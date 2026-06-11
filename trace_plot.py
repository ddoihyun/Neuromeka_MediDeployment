from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


AXIS6_LABELS = ("j1/c1", "j2/c2", "j3/c3", "j4/c4", "j5/c5", "j6/c6")
COMMAND_CANDIDATES = (
    "sent_command",
    "controller_command",
    "command_delta",
    "scaled_delta",
    "limited_velocity",
    "raw_velocity",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a jumping-debug plot PNG from a control_trace_*.csv file. "
            "Example: python trace_plot.py LOG/control_trace_x.csv -o plot.png"
        )
    )
    parser.add_argument("csv", nargs="?", help="Path to control_trace_*.csv")
    parser.add_argument("--input", "-i", dest="input", help="Path to control_trace_*.csv")
    parser.add_argument("--output", "-o", default="plot.png", help="Output PNG path, default: plot.png")
    parser.add_argument("--dpi", type=int, default=150, help="Output PNG DPI, default: 150")
    parser.add_argument(
        "--command",
        default="sent_command",
        help=(
            "Command vector prefix to plot. Default: sent_command. "
            f"Fallback order: {', '.join(COMMAND_CANDIDATES)}"
        ),
    )
    parser.add_argument("--start", type=float, default=None, help="Start time in seconds after first sample")
    parser.add_argument("--end", type=float, default=None, help="End time in seconds after first sample")
    parser.add_argument(
        "--fixed-only",
        action="store_true",
        help="Plot only rows that are fixed-mode samples/skips/enters/exits",
    )
    return parser.parse_args()


def load_libraries():
    try:
        import pandas as pd
        import numpy as np
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise SystemExit(
            "ERROR: pandas, numpy, and matplotlib are required to run trace_plot.py. "
            f"Original import error: {exc}"
        ) from exc
    return pd, np, plt


def resolve_input(args: argparse.Namespace) -> Path:
    raw = args.input or args.csv
    if not raw:
        raise SystemExit("ERROR: provide a CSV path, e.g. python trace_plot.py LOG/control_trace_x.csv")
    path = Path(raw).expanduser().resolve()
    if not path.exists():
        raise SystemExit(f"ERROR: input CSV does not exist: {path}")
    if not path.is_file():
        raise SystemExit(f"ERROR: input path is not a file: {path}")
    return path


def resolve_output(raw: str) -> Path:
    output = Path(raw).expanduser().resolve()
    if output.suffix.lower() != ".png":
        output = output.with_suffix(".png")
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def warn(message: str) -> None:
    print(f"WARNING: {message}", file=sys.stderr)


def read_csv(pd, path: Path):
    try:
        return pd.read_csv(path, low_memory=False)
    except TypeError:
        return pd.read_csv(path)


def numeric(pd, df, column: str):
    if column not in df.columns:
        return pd.Series(float("nan"), index=df.index)
    return pd.to_numeric(df[column], errors="coerce")


def string_series(df, column: str, default: str = ""):
    if column not in df.columns:
        return None
    return df[column].astype("string").fillna(default).str.strip()


def time_axis(pd, np, df):
    for column in ("elapsed_sec", "perf_counter_sec"):
        if column not in df.columns:
            continue
        values = pd.to_numeric(df[column], errors="coerce")
        if values.notna().any():
            first = values.dropna().iloc[0]
            return values - first, column
    if "timestamp" in df.columns:
        values = pd.to_datetime(df["timestamp"], errors="coerce")
        if values.notna().any():
            first = values.dropna().iloc[0]
            return (values - first).dt.total_seconds(), "timestamp"
    warn("no usable elapsed_sec/perf_counter_sec/timestamp column; using row index")
    return pd.Series(np.arange(len(df), dtype=float), index=df.index), "row_index"


def vector(pd, df, prefix: str, length: int = 6):
    columns = [f"{prefix}_{index}" for index in range(length)]
    if not any(column in df.columns for column in columns):
        return None
    data = {
        column: pd.to_numeric(df[column], errors="coerce")
        if column in df.columns
        else pd.Series(float("nan"), index=df.index)
        for column in columns
    }
    out = pd.DataFrame(data)
    return out if out.notna().any().any() else None


def choose_command(pd, df, requested: str):
    prefixes = [requested] + [prefix for prefix in COMMAND_CANDIDATES if prefix != requested]
    for prefix in prefixes:
        data = vector(pd, df, prefix, 6)
        if data is not None:
            if prefix != requested:
                warn(f"{requested}_* unavailable/empty; using {prefix}_* instead")
            return prefix, data
    warn("no command vector columns found")
    return "", None


def filter_rows(pd, df, t, args: argparse.Namespace):
    mask = t.notna()
    if args.start is not None:
        mask &= t >= args.start
    if args.end is not None:
        mask &= t <= args.end
    if args.fixed_only:
        record_type = string_series(df, "record_type")
        fixed_mode = string_series(df, "fixed_mode_name")
        fixed_active = numeric(pd, df, "fixed_active")
        fixed_mask = pd.Series(False, index=df.index)
        if record_type is not None:
            fixed_mask |= record_type.str.startswith("fixed", na=False)
        if fixed_mode is not None:
            fixed_mask |= fixed_mode.ne("") & fixed_mode.ne("inactive")
        fixed_mask |= fixed_active.fillna(0).ne(0)
        mask &= fixed_mask
    filtered = df.loc[mask].reset_index(drop=True)
    filtered_t = t.loc[mask].reset_index(drop=True).astype(float)
    if filtered.empty:
        raise SystemExit("ERROR: no rows remain after filtering.")
    return filtered, filtered_t


def category_codes(pd, series, preferred: Optional[Sequence[str]] = None):
    if series is None:
        return None, []
    values = series.astype("string").fillna("unknown").replace("", "unknown")
    labels: List[str] = []
    if preferred:
        for label in preferred:
            if (values == label).any() and label not in labels:
                labels.append(label)
    for label in values:
        label = str(label)
        if label not in labels:
            labels.append(label)
    mapping = {label: index for index, label in enumerate(labels)}
    return values.map(mapping), labels


def add_event_lines(ax, t, df, color: str = "0.25") -> None:
    if "record_type" not in df.columns:
        return
    record_type = df["record_type"].astype("string").fillna("")
    important = record_type.isin(["fixed_enter", "fixed_exit"])
    if "skip_reason" in df.columns:
        skip_reason = df["skip_reason"].astype("string").fillna("")
        important |= skip_reason.isin(["robot_not_tele_op", "cockpit_released", "fixed_not_requested"])
    event_times = t.loc[important]
    event_types = record_type.loc[important]
    for index, event_time in event_times.items():
        if not event_time == event_time:
            continue
        event = str(event_types.loc[index])
        linestyle = "--" if event == "fixed_enter" else ":"
        ax.axvline(float(event_time), color=color, linewidth=0.8, linestyle=linestyle, alpha=0.35)


def plot_opstate_mode(pd, ax, t, df) -> None:
    ax.set_title("Robot OpState and Fixed/Control Mode")
    robot_state = numeric(pd, df, "robot_state")
    robot_state_name = string_series(df, "robot_state_name")
    if robot_state.notna().any():
        ax.step(t, robot_state, where="post", color="black", linewidth=1.2, label="robot_state")
        ax.set_ylabel("robot_state")
    elif robot_state_name is not None:
        codes, labels = category_codes(pd, robot_state_name)
        ax.step(t, codes, where="post", color="black", linewidth=1.2, label="robot_state_name")
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels)
    else:
        ax.text(0.5, 0.55, "No robot_state data", transform=ax.transAxes, ha="center")

    ax2 = ax.twinx()
    mode = string_series(df, "fixed_mode_name")
    if mode is None or not mode.ne("").any():
        mode = string_series(df, "control_mode_name")
    codes, labels = category_codes(pd, mode, preferred=["inactive", "fixed_line", "fixed_point", "fixed_plane"])
    if codes is not None:
        ax2.step(t, codes, where="post", color="tab:blue", linewidth=1.0, alpha=0.85, label="mode")
        ax2.set_yticks(range(len(labels)))
        ax2.set_yticklabels(labels)
        ax2.set_ylabel("mode")
    add_event_lines(ax, t, df)
    ax.grid(True, alpha=0.25)


def plot_state_gates(pd, ax, t, df) -> None:
    ax.set_title("State Gates: cockpit / move_sent / fixed_active / TELE_OP")
    gates: List[Tuple[str, object]] = []
    for column in ("cockpit_pressed", "move_sent", "fixed_active", "button_pressed"):
        if column in df.columns:
            gates.append((column, numeric(pd, df, column)))
    if "robot_state_name" in df.columns:
        teleop = df["robot_state_name"].astype("string").fillna("").eq("TELE_OP").astype(float)
        gates.append(("robot_state == TELE_OP", teleop))
    elif "robot_state" in df.columns:
        teleop = numeric(pd, df, "robot_state").eq(17).astype(float)
        gates.append(("robot_state == 17", teleop))

    if not gates:
        ax.text(0.5, 0.5, "No state gate data", transform=ax.transAxes, ha="center", va="center")
    for offset, (label, series) in enumerate(gates):
        if series.notna().any():
            ax.step(t, series.astype(float) + offset * 1.2, where="post", linewidth=1.0, label=label)
    ax.set_yticks([index * 1.2 for index in range(len(gates))])
    ax.set_yticklabels([label for label, _ in gates])
    add_event_lines(ax, t, df)
    ax.grid(True, axis="x", alpha=0.25)
    ax.legend(loc="upper right", fontsize=8, ncol=3)


def plot_vector_axes(np, ax, t, data, title: str, ylabel: str, labels: Sequence[str]) -> None:
    ax.set_title(title)
    if data is None:
        ax.text(0.5, 0.5, f"No {ylabel} data", transform=ax.transAxes, ha="center", va="center")
        ax.grid(True, alpha=0.25)
        return
    colors = ax.figure.canvas.manager if False else None
    for index, column in enumerate(data.columns):
        if data[column].notna().any():
            ax.plot(t, data[column], linewidth=0.9, label=labels[index])
    values = data.to_numpy(dtype=float)
    if np.isfinite(values).any():
        norm = np.sqrt(np.nansum(values * values, axis=1))
        ax.plot(t, norm, color="black", linewidth=1.6, alpha=0.85, label="norm")
    add_event_lines(ax, t, data.join(data.iloc[:, :0]))
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper right", fontsize=8, ncol=4)


def plot_tau(pd, np, ax, t, df) -> None:
    ax.set_title("Joint External Torque: tau_ext (j1..j6)")
    tau_ext = vector(pd, df, "tau_ext", 6)
    if tau_ext is None:
        ax.text(0.5, 0.5, "No tau_ext data", transform=ax.transAxes, ha="center", va="center")
        ax.grid(True, alpha=0.25)
        return
    for index, column in enumerate(tau_ext.columns):
        ax.plot(t, tau_ext[column], linewidth=0.9, label=f"tau_ext {AXIS6_LABELS[index]}")
    values = tau_ext.to_numpy(dtype=float)
    ax.plot(t, np.sqrt(np.nansum(values * values, axis=1)), color="black", linewidth=1.6, label="||tau_ext||")
    add_event_lines(ax, t, df)
    ax.set_ylabel("Nm")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper right", fontsize=8, ncol=4)


def plot_command(pd, np, ax, t, df, command_prefix: str, command) -> None:
    ax.set_title(f"Command: {command_prefix}_0..5")
    if command is None:
        ax.text(0.5, 0.5, "No command data", transform=ax.transAxes, ha="center", va="center")
        ax.grid(True, alpha=0.25)
        return
    for index, column in enumerate(command.columns):
        ax.plot(t, command[column], linewidth=0.9, label=f"{command_prefix} {AXIS6_LABELS[index]}")
    values = command.to_numpy(dtype=float)
    ax.plot(t, np.sqrt(np.nansum(values * values, axis=1)), color="black", linewidth=1.6, label="command norm")
    add_event_lines(ax, t, df)
    ax.set_ylabel(command_prefix)
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper right", fontsize=8, ncol=4)


def plot_jump_metric(pd, np, ax, t, df, command_prefix: str, command) -> None:
    ax.set_title("Jump Metrics: command consecutive step and command_delta")
    handles = []
    labels = []
    if command is not None:
        step = command.diff().abs().max(axis=1)
        line = ax.plot(t, step, color="tab:red", linewidth=1.1, label=f"max |diff({command_prefix})|")[0]
        handles.append(line)
        labels.append(line.get_label())
    command_delta = vector(pd, df, "command_delta", 6)
    if command_delta is not None:
        metric = command_delta.abs().max(axis=1)
        line = ax.plot(t, metric, color="tab:orange", linewidth=1.1, label="max |command_delta|")[0]
        handles.append(line)
        labels.append(line.get_label())
    scaled_delta = vector(pd, df, "scaled_delta", 6)
    if scaled_delta is not None:
        metric = scaled_delta.abs().max(axis=1)
        line = ax.plot(t, metric, color="tab:purple", linewidth=1.0, alpha=0.85, label="max |scaled_delta|")[0]
        handles.append(line)
        labels.append(line.get_label())
    add_event_lines(ax, t, df)
    ax.set_ylabel("step magnitude")
    ax.grid(True, alpha=0.25)
    if handles:
        ax.legend(handles, labels, loc="upper right", fontsize=8, ncol=3)
    else:
        ax.text(0.5, 0.5, "No command jump data", transform=ax.transAxes, ha="center", va="center")


def plot_line_pipeline(pd, ax, t, df) -> None:
    ax.set_title("Fixed-Line Pipeline: line input/filter and z command delta")
    plotted = False
    for column, style, label in (
        ("line_input_velocity", "-", "line_input_velocity"),
        ("line_filtered_velocity", "-", "line_filtered_velocity"),
        ("raw_velocity_2", "--", "raw_velocity z"),
        ("limited_velocity_2", "--", "limited_velocity z"),
        ("command_delta_2", ":", "command_delta z"),
    ):
        if column in df.columns:
            series = numeric(pd, df, column)
            if series.notna().any():
                ax.plot(t, series, linestyle=style, linewidth=1.1, label=label)
                plotted = True
    add_event_lines(ax, t, df)
    ax.set_ylabel("line / z command")
    ax.grid(True, alpha=0.25)
    if plotted:
        ax.legend(loc="upper right", fontsize=8, ncol=3)
    else:
        ax.text(0.5, 0.5, "No line pipeline data", transform=ax.transAxes, ha="center", va="center")


def plot_tau_processing(pd, np, ax, t, df) -> None:
    ax.set_title("Tau Processing Norms: raw/debiased/filtered/processed")
    plotted = False
    for prefix, label in (
        ("tau_ext", "||tau_ext||"),
        ("tau_debiased", "||tau_debiased||"),
        ("tau_filtered", "||tau_filtered||"),
        ("tau_processed", "||tau_processed||"),
    ):
        data = vector(pd, df, prefix, 6)
        if data is None:
            continue
        values = data.to_numpy(dtype=float)
        ax.plot(t, np.sqrt(np.nansum(values * values, axis=1)), linewidth=1.1, label=label)
        plotted = True
    for column, label in (
        ("tau_filter_alpha", "tau_filter_alpha"),
        ("line_input_stabilizer_alpha", "line_stabilizer_alpha"),
    ):
        if column in df.columns:
            series = numeric(pd, df, column)
            if series.notna().any():
                ax.plot(t, series, linewidth=0.9, linestyle=":", label=label)
                plotted = True
    add_event_lines(ax, t, df)
    ax.set_ylabel("norm / alpha")
    ax.grid(True, alpha=0.25)
    if plotted:
        ax.legend(loc="upper right", fontsize=8, ncol=4)
    else:
        ax.text(0.5, 0.5, "No tau processing data", transform=ax.transAxes, ha="center", va="center")


def plot_pose_debug(pd, np, ax, t, df) -> None:
    ax.set_title("Pose / Constraint Debug")
    plotted = False
    p = vector(pd, df, "p", 6)
    if p is not None:
        xyz = p.iloc[:, 0:3]
        origin = xyz.dropna().iloc[0] if xyz.notna().any().any() else None
        if origin is not None:
            disp = xyz.subtract(origin, axis=1)
            values = disp.to_numpy(dtype=float)
            ax.plot(t, np.sqrt(np.nansum(values * values, axis=1)), label="TCP xyz displacement norm")
            plotted = True
    for column, label in (
        ("constraint_error_norm", "constraint_error_norm"),
        ("singularity_speed_scale", "singularity_speed_scale"),
    ):
        if column in df.columns:
            series = numeric(pd, df, column)
            if series.notna().any():
                ax.plot(t, series, linewidth=1.0, label=label)
                plotted = True
    add_event_lines(ax, t, df)
    ax.set_ylabel("pose / constraint")
    ax.grid(True, alpha=0.25)
    if plotted:
        ax.legend(loc="upper right", fontsize=8, ncol=3)
    else:
        ax.text(0.5, 0.5, "No pose/constraint data", transform=ax.transAxes, ha="center", va="center")


def summarize(pd, np, df, command_prefix: str, command) -> str:
    parts = [f"rows={len(df)}", f"command={command_prefix or 'none'}"]
    if "record_type" in df.columns:
        fixed_samples = int(df["record_type"].astype("string").fillna("").eq("fixed_sample").sum())
        parts.append(f"fixed_sample={fixed_samples}")
    if command is not None:
        step = command.diff().abs().max(axis=1)
        max_index = step.idxmax()
        if max_index == max_index and step.notna().any():
            parts.append(f"max_command_step={float(step.loc[max_index]):.4g}@row{int(max_index)}")
    tau_ext = vector(pd, df, "tau_ext", 6)
    if tau_ext is not None:
        parts.append(f"max_tau_ext={float(tau_ext.abs().max().max()):.4g}")
    return " | ".join(parts)


def build_plot(args: argparse.Namespace) -> Path:
    pd, np, plt = load_libraries()
    input_path = resolve_input(args)
    output_path = resolve_output(args.output)

    df = read_csv(pd, input_path)
    if df.empty:
        raise SystemExit(f"ERROR: input CSV has no rows: {input_path}")
    t, time_source = time_axis(pd, np, df)
    df, t = filter_rows(pd, df, t, args)
    command_prefix, command = choose_command(pd, df, args.command)

    fig, axes = plt.subplots(8, 1, figsize=(18, 22), sharex=True)
    fig.suptitle(f"Jumping Debug Trace: {input_path.name}", fontsize=16)

    plot_opstate_mode(pd, axes[0], t, df)
    plot_state_gates(pd, axes[1], t, df)
    plot_tau(pd, np, axes[2], t, df)
    plot_tau_processing(pd, np, axes[3], t, df)
    plot_command(pd, np, axes[4], t, df, command_prefix, command)
    plot_jump_metric(pd, np, axes[5], t, df, command_prefix, command)
    plot_line_pipeline(pd, axes[6], t, df)
    plot_pose_debug(pd, np, axes[7], t, df)

    if len(t) > 0:
        axes[-1].set_xlabel(f"time from first sample (s), source={time_source}")
        axes[-1].set_xlim(float(t.min()), float(t.max()))

    summary = summarize(pd, np, df, command_prefix, command)
    fig.text(0.01, 0.01, summary, ha="left", va="bottom", fontsize=9)
    fig.tight_layout(rect=(0, 0.025, 1, 0.965))
    fig.savefig(output_path, dpi=args.dpi)
    plt.close(fig)
    return output_path


def main() -> None:
    output_path = build_plot(parse_args())
    print(f"Saved plot: {output_path}")


if __name__ == "__main__":
    main()
