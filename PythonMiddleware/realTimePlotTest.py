import argparse
from interfaces.rtde_socket_client import RTDESocketClient
from matplotlib.animation import FuncAnimation
import matplotlib.pyplot as plt
import matplotlib
import numpy as np
import tkinter as tk

def set_window_position(fig, x, y):
    """
    Set the window position of the matplotlib figure.
    This works by getting the window manager and using tkinter to set position.
    """
    # Use tkinter to set the window position
    manager = fig.canvas.manager
    window = manager.window
    window.geometry(f"+{x}+{y}")

def main(step_ip):
    # RTDE socket client initialization
    rtde = RTDESocketClient(step_ip)

    matplotlib.use("TkAgg")

    # Data labels for the subplots
    data_labels = ['Torque', 'Joint Position', 'Joint Velocity', 'Joint Position Error', 'Joint Velocity Error']

    # Initialize data sources
    time_steps = list(range(80))
    y_data = [[[0] * len(time_steps) for _ in range(6)] for _ in range(5)]  # For 5 different data categories

    # Define y-axis limits for each joint and each data category
    y_limits = {
        'Torque': [(-350, 350), (-350, 350), (-200, 200), (-30, 30), (-20, 20), (-20, 20)],  # Example: Same limits for all joints
        'Joint Position': [(-180, 180), (-100, 100), (-150, 150), (-200, 200), (-150, 150), (-250, 250)],  # Different limits for each joint
        'Joint Velocity': [(-150, 150), (-150, 150), (-150, 150), (-150, 150), (-150, 150), (-150, 150)],
        'Joint Position Error': [(-1.5, 1.5)] * 6,  # Same limits for all joints
        'Joint Velocity Error': [(-3, 3)] * 6   # Same limits for all joints
    }

    y_labels = {
        'Torque': 'Torque (Nm)',
        'Joint Position': 'Position (Degrees)',
        'Joint Velocity': 'Velocity (Deg/s)',
        'Joint Position Error': 'Position Error (Degrees)',
        'Joint Velocity Error': 'Velocity Error (Deg/s)'
    }

    # Create the plot with 3 separate figures for different categories
    fig_torque, axes_torque = plt.subplots(2, 3, figsize=(9.5, 5), constrained_layout=True)  # For torque
    fig_pos_error, axes_pos_error = plt.subplots(2, 3, figsize=(9.5, 5), constrained_layout=True)  # For position error
    fig_vel_error, axes_vel_error = plt.subplots(2, 3, figsize=(9.5, 5), constrained_layout=True)  # For velocity error

    # Set the window positions
    set_window_position(fig_torque, 0, 0)  # Top-left corner
    set_window_position(fig_pos_error, 950, 0)  # Top-right corner
    set_window_position(fig_vel_error, 0, 530)  # Bottom-left corner

    axes_torque = axes_torque.flatten()  # Flatten the 2D axes array into 1D for easier indexing
    axes_pos_error = axes_pos_error.flatten()
    axes_vel_error = axes_vel_error.flatten()

    # Set up each subplot for torque, position error, and velocity error
    lines_torque, lines_pos_error, lines_vel_error = [], [], []
    text_labels_torque, text_labels_pos_error, text_labels_vel_error = [], [], []

    for col in range(6):  # Now we plot all 6 joints
        # Set up plots for torque
        ax_torque = axes_torque[col]
        line_torque, = ax_torque.plot(time_steps, [0] * len(time_steps), 'b-')
        ax_torque.set_title(f"Torque - Joint {col + 1}", fontsize=10)  # Reduced title font size
        ax_torque.set_ylim(y_limits['Torque'][col])
        ax_torque.set_ylabel(y_labels['Torque'])
        ax_torque.set_xlim(0, len(time_steps))
        
        # Add text label to display the latest value, max, and RMS
        text_torque = ax_torque.text(len(time_steps) - 1, 0, '', fontsize=8, verticalalignment='bottom', horizontalalignment='right', color='red')
        text_max_torque = ax_torque.text(len(time_steps) - 1, ax_torque.get_ylim()[1] * 0.8, '', fontsize=7, verticalalignment='bottom', color='green')
        text_rms_torque = ax_torque.text(len(time_steps) - 1, ax_torque.get_ylim()[1] * 0.6, '', fontsize=7, verticalalignment='bottom', color='blue')
        lines_torque.append(line_torque)
        text_labels_torque.append((text_torque, text_max_torque, text_rms_torque))

        # Set up plots for position error
        ax_pos_error = axes_pos_error[col]
        line_pos_error, = ax_pos_error.plot(time_steps, [0] * len(time_steps), 'b-')
        ax_pos_error.set_title(f"Position Error - Joint {col + 1}", fontsize=10)  # Reduced title font size
        ax_pos_error.set_ylim(y_limits['Joint Position Error'][col])
        ax_pos_error.set_ylabel(y_labels['Joint Position Error'])
        ax_pos_error.set_xlim(0, len(time_steps))
        
        # Add text label to display the latest value, max, and RMS
        text_pos_error = ax_pos_error.text(len(time_steps) - 1, 0, '', fontsize=8, verticalalignment='bottom', horizontalalignment='right', color='red')
        text_max_pos_error = ax_pos_error.text(len(time_steps) - 1, ax_pos_error.get_ylim()[1] * 0.8, '', fontsize=7, verticalalignment='bottom', color='green')
        text_rms_pos_error = ax_pos_error.text(len(time_steps) - 1, ax_pos_error.get_ylim()[1] * 0.6, '', fontsize=7, verticalalignment='bottom', color='blue')
        lines_pos_error.append(line_pos_error)
        text_labels_pos_error.append((text_pos_error, text_max_pos_error, text_rms_pos_error))

        # Set up plots for velocity error
        ax_vel_error = axes_vel_error[col]
        line_vel_error, = ax_vel_error.plot(time_steps, [0] * len(time_steps), 'b-')
        ax_vel_error.set_title(f"Velocity Error - Joint {col + 1}", fontsize=10)  # Reduced title font size
        ax_vel_error.set_ylim(y_limits['Joint Velocity Error'][col])
        ax_vel_error.set_ylabel(y_labels['Joint Velocity Error'])
        ax_vel_error.set_xlim(0, len(time_steps))
        
        # Add text label to display the latest value, max, and RMS
        text_vel_error = ax_vel_error.text(len(time_steps) - 1, 0, '', fontsize=8, verticalalignment='bottom', horizontalalignment='right', color='red')
        text_max_vel_error = ax_vel_error.text(len(time_steps) - 1, ax_vel_error.get_ylim()[1] * 0.8, '', fontsize=7, verticalalignment='bottom', color='green')
        text_rms_vel_error = ax_vel_error.text(len(time_steps) - 1, ax_vel_error.get_ylim()[1] * 0.6, '', fontsize=7, verticalalignment='bottom', color='blue')
        lines_vel_error.append(line_vel_error)
        text_labels_vel_error.append((text_vel_error, text_max_vel_error, text_rms_vel_error))

    def update_torque(frame):
        # Retrieve the latest data for torque
        control_state = rtde.GetControlState()
        torque = control_state['tau']

        # Update the torque data for each joint and display the latest point value
        for col in range(6):
            y_data[0][col].pop(0)
            y_data[0][col].append(torque[col])
            lines_torque[col].set_ydata(y_data[0][col])

            # Calculate Max and RMS
            max_value = max(y_data[0][col])
            rms_value = np.sqrt(np.mean(np.square(y_data[0][col])))

            # Get y-limits for dynamic text placement
            ylim = axes_torque[col].get_ylim()

            # Update the text with the latest point value, max, and RMS at the upper-left corner
            text_labels_torque[col][0].set_position((len(time_steps) - 1, y_data[0][col][0]))  # Current value at upper-left
            text_labels_torque[col][0].set_text(f'{round(y_data[0][col][0], 4)}')
            #  text_labels_torque[col].set_position((len(time_steps) - 1, torque[col]))
            # text_labels_torque[col].set_text(f'{round(torque[col], 4)}')

            text_labels_torque[col][1].set_position((0, ylim[1] - 0.1 * (ylim[1] - ylim[0])))  # Max value at upper-left
            text_labels_torque[col][1].set_text(f'Max: {round(max_value, 4)}')

            text_labels_torque[col][2].set_position((0, ylim[1] - 0.2 * (ylim[1] - ylim[0])))  # RMS value below Max
            text_labels_torque[col][2].set_text(f'RMS: {round(rms_value, 4)}')

        return lines_torque + [text for sublist in text_labels_torque for text in sublist]


    def update_pos_error(frame):
        # Retrieve the latest data for position error
        control_state = rtde.GetControlState()
        jpose = control_state['q']
        jpose_desired = control_state['qdes']
        jposeError = np.degrees(np.array(jpose) - np.array(jpose_desired))

        # Update the position error data for each joint and display the latest point value
        for col in range(6):
            y_data[3][col].pop(0)
            y_data[3][col].append(jposeError[col])
            lines_pos_error[col].set_ydata(y_data[3][col])

            # Calculate Max and RMS
            max_value = max(y_data[3][col])
            rms_value = np.sqrt(np.mean(np.square(y_data[3][col])))

            # Get y-limits for dynamic text placement
            ylim = axes_pos_error[col].get_ylim()

            # Update the text with the latest point value, max, and RMS at the upper-left corner
            text_labels_pos_error[col][0].set_position((len(time_steps) - 1, jposeError[col]))  # Current value at upper-left
            text_labels_pos_error[col][0].set_text(f'{round(jposeError[col], 4)}')

            text_labels_pos_error[col][1].set_position((0, ylim[1] - 0.1 * (ylim[1] - ylim[0])))  # Max value at upper-left
            text_labels_pos_error[col][1].set_text(f'Max: {round(max_value, 4)}')

            text_labels_pos_error[col][2].set_position((0, ylim[1] - 0.2 * (ylim[1] - ylim[0])))  # RMS value below Max
            text_labels_pos_error[col][2].set_text(f'RMS: {round(rms_value, 4)}')

        return lines_pos_error + [text for sublist in text_labels_pos_error for text in sublist]


    def update_vel_error(frame):
        # Retrieve the latest data for velocity error
        control_state = rtde.GetControlState()
        jvel = control_state['qdot']
        jvel_desired = control_state['qdotdes']

        # Calculate velocity error and convert to degrees
        jvelError = np.degrees(np.array(jvel) - np.array(jvel_desired))

        # Update the velocity error data for each joint and display the latest point value
        for col in range(6):
            y_data[4][col].pop(0)
            y_data[4][col].append(jvelError[col])
            lines_vel_error[col].set_ydata(y_data[4][col])

            # Calculate Max and RMS
            max_value = max(y_data[4][col])
            rms_value = np.sqrt(np.mean(np.square(y_data[4][col])))

            # Get y-limits for dynamic text placement
            ylim = axes_vel_error[col].get_ylim()

            # Update the text with the latest point value, max, and RMS at the upper-left corner
            text_labels_vel_error[col][0].set_position((len(time_steps) - 1, jvelError[col]))  # Current value at upper-left
            text_labels_vel_error[col][0].set_text(f'{round(jvelError[col], 4)}')

            text_labels_vel_error[col][1].set_position((0, ylim[1] - 0.1 * (ylim[1] - ylim[0])))  # Max value at upper-left
            text_labels_vel_error[col][1].set_text(f'Max: {round(max_value, 4)}')

            text_labels_vel_error[col][2].set_position((0, ylim[1] - 0.2 * (ylim[1] - ylim[0])))  # RMS value below Max
            text_labels_vel_error[col][2].set_text(f'RMS: {round(rms_value, 4)}')

        return lines_vel_error + [text for sublist in text_labels_vel_error for text in sublist]



    # Start the animation for all figures
    ani_torque = FuncAnimation(fig_torque, update_torque, frames=range(100), interval=50, blit=True)
    ani_pos_error = FuncAnimation(fig_pos_error, update_pos_error, frames=range(100), interval=50, blit=True)
    ani_vel_error = FuncAnimation(fig_vel_error, update_vel_error, frames=range(100), interval=50, blit=True)

    plt.show()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Real-time robot monitoring with RTDE.")
    parser.add_argument("ip", type=str, help="IP address of the robot controller.")
    args = parser.parse_args()
    main(args.ip)
