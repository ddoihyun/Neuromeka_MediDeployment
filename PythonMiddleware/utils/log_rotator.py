from time import sleep
import os
import sys
import select

MAX_LOG_SIZE = 4 * 1024 * 1024  # 4 MB, about 1 hour with log_level 4
ROTATE_COUNT = 32  # about 1 day for single boot

def rotate_log_file(base_path, max_count):
    """
    Rotates log files up to max_count.
    Older files are deleted.
    """
    for i in range(max_count - 1, 0, -1):
        old_file = f"{base_path}.{i}"
        new_file = f"{base_path}.{i + 1}"
        if os.path.exists(old_file):
            os.rename(old_file, new_file)

    # Move current log to .1
    if os.path.exists(base_path):
        os.rename(base_path, f"{base_path}.1")

def main():
    log_pipe_path = sys.argv[-2]
    log_file_path = sys.argv[-1]
    print(f"Open Log Pipe {log_pipe_path}")
    pipe_fd = os.open(log_pipe_path, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(pipe_fd, 'r') as pipe:
        while True:
            flag_rotate = False
            print(f"Open Log File {log_file_path}")
            with open(log_file_path, 'a') as log_file:
                while not flag_rotate:  # repeat read and write
                    # Read from the pipe
                    ready, _, _ = select.select([pipe], [], [], 1)  # 1-second timeout
                    if ready:
                        buffer = pipe.read()
                        print(buffer, end="")
                        log_file.write(buffer)

                        # Check log file size and rotate if necessary
                        if os.path.getsize(log_file_path) >= MAX_LOG_SIZE:
                            flag_rotate = True # exit loop to close file before rotate
            # rotate log file after log_file closed (outside "with log_file")
            if flag_rotate:
                rotate_log_file(log_file_path, ROTATE_COUNT)
    # pipe.close()
    # os.close(pipe)


if __name__ == "__main__":
    main()
