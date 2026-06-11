from interfaces.control_socket_client import ControlSocketClient
import psutil
import sys, json, grpc, time
import paramiko
import csv
import math

from matplotlib.pyplot import figure
import matplotlib.pyplot as plt


PI = math.pi
RAD2DEG = 180/PI
DEG2RAD = PI/180

class PlotTool:
    def __init__(self, control=None):
        self.control = control
        self.record = {
            "t": [], "cycle_time": [], "period": [],
            **{f"q{i}": [] for i in range(1, 7)},
            **{f"qdot{i}": [] for i in range(1, 7)},
            **{f"qddot{i}": [] for i in range(1, 7)},
            **{f"tau{i}": [] for i in range(1, 7)},
            **{f"tauact{i}": [] for i in range(1, 7)},
            **{f"qd{i}": [] for i in range(1, 7)},
            **{f"qdotd{i}": [] for i in range(1, 7)},
            **{f"qddotd{i}": [] for i in range(1, 7)},
            **{f"p{i}": [] for i in range(1, 7)},
            **{f"pd{i}": [] for i in range(1, 7)},
            **{f"qe{i}": [] for i in range(1, 7)},
            **{f"pe{i}": [] for i in range(1, 7)},
            **{f"fe{i}": [] for i in range(1, 7)},
            **{f"fdes{i}": [] for i in range(1, 7)},
            **{f"fact{i}": [] for i in range(1, 7)}
        }

    def start_log(self):
        int_vars_to_set = [{"addr": 300, "value": 1}]
        self.control.SetIntVariable(int_vars_to_set)


    def end_log(self):
        int_vars_to_set = [{"addr": 300, "value": 2}]
        self.control.SetIntVariable(int_vars_to_set)

    def load_data_6dof(self, file_name, step_ip):

        # Saved folder paramiko
        file_to_directory = '/home/user/release/IndyDeployment/RTLog'
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(step_ip, username='root', password='root')

        # open the remote file using `sftp`
        sftp = ssh.open_sftp()
        remote_file = sftp.open(file_to_directory+'/'+file_name)

        # read the contents of the file using `csv` library
        reader = csv.reader(remote_file, delimiter=",")
            

        for line in reader:
            # Appending values to lists
            self.record["t"].append(float(line[0]))
            self.record["cycle_time"].append(float(line[1]))
            self.record["period"].append(float(line[2]))

            for i in range(1, 7):
                self.record[f"q{i}"].append(float(line[2 + i]))
                self.record[f"qdot{i}"].append(float(line[8 + i]))
                self.record[f"qddot{i}"].append(float(line[14 + i]))
                self.record[f"tau{i}"].append(float(line[20 + i]))
                self.record[f"tauact{i}"].append(float(line[26 + i]))
                self.record[f"qd{i}"].append(float(line[32 + i]))
                self.record[f"qdotd{i}"].append(float(line[38 + i]))
                self.record[f"qddotd{i}"].append(float(line[44 + i]))
                self.record[f"p{i}"].append(float(line[50 + i]))
                self.record[f"pd{i}"].append(float(line[56 + i]))
                self.record[f"fdes{i}"].append(float(line[62 + i]))
                self.record[f"fact{i}"].append(float(line[68 + i]))

                # Compute Joint and Task Position errors
                self.record[f"qe{i}"].append(self.record[f"qd{i}"][-1] - self.record[f"q{i}"][-1])
                self.record[f"pe{i}"].append(self.record[f"pd{i}"][-1] - self.record[f"p{i}"][-1])
                self.record[f"fe{i}"].append(self.record[f"fdes{i}"][-1] - self.record[f"fact{i}"][-1])



    def load_data_7dof(self, step_ip, file_name):
        # Saved folder paramiko
        file_to_directory = '/home/user/release/IndyDeployment/RTLog'
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(step_ip, username='root', password='root')

        # open the remote file using `sftp`
        sftp = ssh.open_sftp()
        remote_file = sftp.open(file_to_directory+'/'+file_name)

        # read the contents of the file using `csv` library
        reader = csv.reader(remote_file, delimiter=",")

        # Initializing lists
        for line in reader:
            # Appending values to lists
            self.record["t"].append(float(line[0]))
            self.record["cycle_time"].append(float(line[1]))
            self.record["period"].append(float(line[2]))

            for i in range(1, 8):
                self.record[f"q{i}"].append(float(line[2 + i]))
                self.record[f"qdot{i}"].append(float(line[9 + i]))
                self.record[f"qddot{i}"].append(float(line[16 + i]))
                self.record[f"tau{i}"].append(float(line[23 + i]))
                self.record[f"tauact{i}"].append(float(line[30 + i]))
                self.record[f"qd{i}"].append(float(line[37 + i]))
                self.record[f"qdotd{i}"].append(float(line[44 + i]))
                self.record[f"qddotd{i}"].append(float(line[51 + i]))
                self.record[f"p{i}"].append(float(line[58 + i]))
                self.record[f"pd{i}"].append(float(line[65 + i]))

                # Compute Joint and Task Position errors
                self.record[f"qe{i}"].append(self.record[f"qd{i}"][-1] - self.record[f"q{i}"][-1])
                self.record[f"pe{i}"].append(self.record[f"pd{i}"][-1] - self.record[f"p{i}"][-1])



    def plot_robot_path(self):
        plt.figure(figsize=(8, 6), dpi=80)
        plt.plot(self.record['p1'], self.record['p2'], 'b', label='Actual Path')
        plt.xlabel('x Position (m)')
        plt.ylabel('y Position (m)')
        plt.title('Robot Path in x-y Plane')
        plt.legend()
        plt.grid(True)
        plt.show()

    def plot_robot_and_desired_path(self):
        plt.figure(figsize=(8, 6), dpi=80)
        plt.plot(self.record['p1'], self.record['p2'], 'b', label='Actual Path')
        plt.plot(self.record['pd1'], self.record['pd2'], 'r--', label='Desired Path')
        plt.xlabel('x Position (m)')
        plt.ylabel('y Position (m)')
        plt.title('Robot and Desired Path in x-y Plane')
        plt.legend()
        plt.grid(True)
        plt.show()

    def plot_robot_and_desired_force(self):
        plt.figure(figsize=(8, 6), dpi=80)
        plt.plot(self.record['t'], self.record['fact1'], 'b', label='Actual Path')
        plt.plot(self.record['t'], self.record['fdes1'], 'r--', label='Desired Path')
        plt.xlabel('x Time (s)')
        plt.ylabel('y Force (Nm)')
        plt.title('Force tracking plot')
        plt.legend()
        plt.grid(True)
        plt.show()

    ## Joint plots
    def plot_joint_pos(self, unit='rad'):
        fig, axes = plt.subplots(6, 1, figsize=(10, 15), dpi=80)
        for i, ax in enumerate(axes, start=1):
            if unit=='deg':
                q = [x*RAD2DEG for x in self.record[f'q{i}']]
                qd = [x*RAD2DEG for x in self.record[f'qd{i}']]                
                ax.set_ylabel(f'q{i}: joint position (deg)')
            elif unit=='rad':
                q = self.record[f'q{i}']
                qd = self.record[f'qd{i}']                
                ax.set_ylabel(f'q{i}: joint position (rad)')
            ax.plot(self.record['t'], q, 'b', self.record['t'], qd, 'r--')
            ax.set_xlabel('Time [sec]')            
            ax.grid(True)            
            max_qd = max(qd)
            min_qd = min(qd)            
            ax.text(self.record['t'][qd.index(max_qd)], max_qd, f'Max qd: {max_qd:.2f}', color='red')
            ax.text(self.record['t'][qd.index(min_qd)], min_qd, f'Min qd: {min_qd:.2f}', color='red', verticalalignment='top')
        fig.suptitle('Joint Positions')
        plt.tight_layout()
        plt.show()        
        


    def plot_joint_vel(self, unit='rad'):
        fig, axes = plt.subplots(6, 1, figsize=(10, 15), dpi=80)
        for i, ax in enumerate(axes, start=1):
            if unit=='deg':
                qdot = [x*RAD2DEG for x in self.record[f'qdot{i}']]
                qdotd = [x*RAD2DEG for x in self.record[f'qdotd{i}']]                
                ax.set_ylabel(f'qdot{i}: joint velocity (deg/s)')
            elif unit=='rad':
                qdot = self.record[f'qdot{i}']
                qdotd = self.record[f'qdotd{i}']                
                ax.set_ylabel(f'qdot{i}: joint velocity (rad/s)')
            ax.plot(self.record['t'], qdot, 'b', self.record['t'], qdotd, 'r--')
            ax.set_xlabel('Time')            
            ax.grid(True)
            max_qdotd = max(qdotd)
            min_qdotd = min(qdotd)            
            ax.text(self.record['t'][qdotd.index(max_qdotd)], max_qdotd, f'Max qdotd: {max_qdotd:.2f}', color='red')
            ax.text(self.record['t'][qdotd.index(min_qdotd)], min_qdotd, f'Min qdotd: {min_qdotd:.2f}', color='red', verticalalignment='top')
        fig.suptitle('Joint Velocity')
        plt.tight_layout()
        plt.show()

    def plot_joint_acc(self, unit='rad'):
        fig, axes = plt.subplots(6, 1, figsize=(10, 15), dpi=80)
        for i, ax in enumerate(axes, start=1):
            if unit=='deg':
                qddot = [x*RAD2DEG for x in self.record[f'qddot{i}']]
                qddotd = [x*RAD2DEG for x in self.record[f'qddotd{i}']]                
                ax.set_ylabel(f'qddot{i}: joint acceleration (deg/s2)')
            elif unit=='rad':
                qddot = self.record[f'qddot{i}']
                qddotd = self.record[f'qddotd{i}']
                ax.set_ylabel(f'qddot{i}: joint acceleration (rad/s2)')
            ax.plot(self.record['t'], qddot, 'b', self.record['t'], qddotd, 'r--')
            ax.set_xlabel('Time')            
            ax.grid(True)
            max_qddotd = max(qddotd)
            min_qddotd = min(qddotd)            
            ax.text(self.record['t'][qddotd.index(max_qddotd)], max_qddotd, f'Max qddotd: {max_qddotd:.2f}', color='red')
            ax.text(self.record['t'][qddotd.index(min_qddotd)], min_qddotd, f'Min qddotd: {min_qddotd:.2f}', color='red', verticalalignment='top')
        fig.suptitle('Joint Acceleration')
        plt.tight_layout()
        plt.show()

    def plot_jerror(self):
        fig, (ax1) = plt.subplots(1, 1, figsize=(10, 5), dpi=80)
        ax1.plot(self.record['t'], self.record['qe1'], self.record['t'], self.record['qe2'], self.record['t'], self.record['qe3'], \
                 self.record['t'], self.record['qe4'], self.record['t'], self.record['qe5'], self.record['t'], self.record['qe6'])
        ax1.set_xlabel('Time')
        ax1.set_ylabel('Error: joint position (rad)')
        ax1.grid(True)
        fig.suptitle('Joint Positino Error')
        plt.tight_layout()
        plt.show()

    def plot_joint_torque(self):
        fig, axes = plt.subplots(6, 1, figsize=(10, 15), dpi=80)
        for i, ax in enumerate(axes, start=1):
            ax.plot(self.record['t'], self.record[f'tau{i}'], 'b', self.record['t'], self.record[f'tauact{i}'], 'r--')
            ax.set_xlabel('Time')
            ax.set_ylabel(f'tau{i}: joint torque')
            ax.grid(True)
        fig.suptitle('Joint Torque')
        plt.tight_layout()
        plt.show()


def plot_task(record):
    def plot_task_pos():
        fig, axes = plt.subplots(6, 1, figsize=(10, 15), dpi=80)
        for i, ax in enumerate(axes, start=1):
            ax.plot(record['t'], record[f'p{i}'], 'b', record['t'], record[f'pd{i}'], 'r--')
            ax.set_xlabel('Time')
            ax.set_ylabel(f'p{i}: Task position (m/rad)')
            ax.grid(True)
        fig.suptitle('Joint Positions')
        plt.tight_layout()
        plt.show()
    def plot_terror():
        fig, (ax1) = plt.subplots(1, 1, figsize=(10, 5), dpi=80)
        ax1.plot(record['t'], record['pe1'], record['t'], record['pe2'], record['t'], record['pe3'], \
                 record['t'], record['pe4'], record['t'], record['pe5'], record['t'], record['pe6'])
        ax1.set_xlabel('Time')
        ax1.set_ylabel('Error: joint position (rad)')
        fig.suptitle('Joint Positions')
        plt.tight_layout()
        ax1.grid(True)

    plot_task_pos()
    plot_terror()
    
