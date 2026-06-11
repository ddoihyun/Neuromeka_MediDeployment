from interfaces.control_socket_client import ControlSocketClient
import psutil
import sys, json, grpc, time
import paramiko
import csv
import math
from matplotlib.pyplot import figure
import matplotlib.pyplot as plt
import numpy as np
import plotly.graph_objs as go
from plotly.offline import iplot
import os
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors

from reportlab.pdfgen import canvas
from reportlab.lib.units import inch

from reportlab.platypus import  Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
import pandas as pd
import numpy as np
from scipy.signal import butter, lfilter

    
PI = math.pi
RAD2DEG = 180/PI
DEG2RAD = PI/180

class PlotTool:
    def __init__(self, control):
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
            **{f"qdote{i}": [] for i in range(1, 7)},
            **{f"pe{i}": [] for i in range(1, 7)},
            **{f"fe{i}": [] for i in range(1, 7)},
            **{f"fdes{i}": [] for i in range(1, 7)},
            **{f"fact{i}": [] for i in range(1, 7)},
            **{f"tauidyn{i}": [] for i in range(1, 7)},
            **{f"tauref{i}": [] for i in range(1, 7)},
            **{f"taugrav{i}": [] for i in range(1, 7)},
            **{f"taufric{i}": [] for i in range(1, 7)},
            **{f"tauext{i}": [] for i in range(1, 7)},
            **{f"tauJts{i}": [] for i in range(1, 7)},
            **{f"tauJtsRaw1{i}": [] for i in range(1, 7)},
            **{f"tauJtsRaw2{i}": [] for i in range(1, 7)},
        }
        
    def start_log(self):
        int_vars_to_set = [{"addr": 300, "value": 1}]
        self.control.SetIntVariable(int_vars_to_set)
        
        
    def end_log(self):
        int_vars_to_set = [{"addr": 300, "value": 2}]
        self.control.SetIntVariable(int_vars_to_set)

    def load_data_6dof(self, step_ip, file_name):
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

            for i in range(1, 7):  # For each joint (1 through 6)
                # Adjusted indexing to correctly align with the CSV structure
                self.record[f"q{i}"].append(float(line[2 + i]))  # Starts from index 3 (4th column) for the first joint
                self.record[f"qdot{i}"].append(float(line[8 + i]))  # Continues sequentially, adjusting the starting index for each parameter
                self.record[f"qddot{i}"].append(float(line[14 + i]))
                self.record[f"tau{i}"].append(float(line[20 + i]))
                self.record[f"tauact{i}"].append(float(line[26 + i]))
                self.record[f"qd{i}"].append(float(line[32 + i]))
                self.record[f"qdotd{i}"].append(float(line[38 + i]))
                self.record[f"qddotd{i}"].append(float(line[44 + i]))
                self.record[f"p{i}"].append(float(line[50 + i]))
                self.record[f"pd{i}"].append(float(line[56 + i]))
                self.record[f"fact{i}"].append(float(line[62 + i]))
                self.record[f"fdes{i}"].append(-float(line[68 + i]))  # Note the negation for fdes
                self.record[f"tauidyn{i}"].append(float(line[74 + i]))
                self.record[f"tauref{i}"].append(float(line[80 + i]))
                self.record[f"taugrav{i}"].append(float(line[86 + i]))
                self.record[f"taufric{i}"].append(float(line[92 + i]))
                self.record[f"tauext{i}"].append(float(line[98 + i]))
                self.record[f"tauJts{i}"].append(float(line[104 + i]))
                self.record[f"tauJtsRaw1{i}"].append(float(line[110 + i]))
                self.record[f"tauJtsRaw2{i}"].append(float(line[116 + i]))


                # Compute Joint and Task Position errors
                self.record[f"qe{i}"].append(self.record[f"qd{i}"][-1] - self.record[f"q{i}"][-1])
                self.record[f"qdote{i}"].append(self.record[f"qdotd{i}"][-1] - self.record[f"qdot{i}"][-1])
                self.record[f"pe{i}"].append(self.record[f"pd{i}"][-1] - self.record[f"p{i}"][-1])
                self.record[f"fe{i}"].append(self.record[f"fdes{i}"][-1] - self.record[f"fact{i}"][-1])



    def load_data_6dof_local2(self, file_name, isExtended):
        file_to_directory = 'C:/Users/yourPath/Data'

        # open the remote file using `sftp`
        remote_file = open(file_to_directory+'/'+file_name)

        # read the contents of the file using `csv` library
        reader = csv.reader(remote_file, delimiter=",")    

        # read the contents of the file using `csv` library
        reader = csv.reader(remote_file, delimiter=",")    
        if isExtended:
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
                    self.record[f"fact{i}"].append(-float(line[68 + i]))
                    self.record[f"tauidyn{i}"].append(float(line[74 + i]))
                    self.record[f"tauref{i}"].append(float(line[80 + i]))
                    self.record[f"taugrav{i}"].append(float(line[86 + i]))
                    self.record[f"taufric{i}"].append(float(line[93 + i]))
                    # self.record[f"tauext{i}"].append(float(line[99 + i]))
                    self.record[f"tauJts{i}"].append(float(line[100 + i]))
                    self.record[f"tauJtsRaw1{i}"].append(float(line[107 + i]))
                    self.record[f"tauJtsRaw2{i}"].append(float(line[114 + i]))

                    # Compute Joint and Task Position errors
                    self.record[f"qe{i}"].append(self.record[f"qd{i}"][-1] - self.record[f"q{i}"][-1])
                    self.record[f"qdote{i}"].append(self.record[f"qdotd{i}"][-1] - self.record[f"qdot{i}"][-1])
                    self.record[f"pe{i}"].append(self.record[f"pd{i}"][-1] - self.record[f"p{i}"][-1])
                    self.record[f"fe{i}"].append(self.record[f"fdes{i}"][-1] - self.record[f"fact{i}"][-1])
        else:
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
                    self.record[f"fact{i}"].append(-float(line[68 + i]))
                    self.record[f"tauidyn{i}"].append(float(line[74 + i]))
                    self.record[f"tauref{i}"].append(float(line[80 + i]))
                    self.record[f"taugrav{i}"].append(float(line[86 + i]))
                    # self.record[f"taufric{i}"].append(float(line[93 + i]))

                    # Compute Joint and Task Position errors
                    self.record[f"qe{i}"].append(self.record[f"qd{i}"][-1] - self.record[f"q{i}"][-1])
                    self.record[f"qdote{i}"].append(self.record[f"qdotd{i}"][-1] - self.record[f"qdot{i}"][-1])
                    self.record[f"pe{i}"].append(self.record[f"pd{i}"][-1] - self.record[f"p{i}"][-1])
                    self.record[f"fe{i}"].append(self.record[f"fdes{i}"][-1] - self.record[f"fact{i}"][-1])


        

    def load_data_6dof_local(self, file_name):
        # Saved folder paramiko
        # file_to_directory = '/home/user/release/IndyDeployment/RTLog'
        file_to_directory = 'C:/Users/yourPath'

        # open the remote file using `sftp`
        remote_file = open(file_to_directory+'/'+file_name)

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
                self.record[f"fact{i}"].append(-float(line[68 + i]))

                # Compute Joint and Task Position errors
                self.record[f"qe{i}"].append(self.record[f"qd{i}"][-1] - self.record[f"q{i}"][-1])
                self.record[f"qdote{i}"].append(self.record[f"qdotd{i}"][-1] - self.record[f"qdot{i}"][-1])
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
                
                

    def calculate_energy(self, joint_number, time_interval):
        """
        Calculate energy consumption based on torque and angular velocity.
        
        :param torque: Array of torque measurements.
        :param angular_velocity: Array of angular velocity measurements.
        :param time_interval: Time interval between measurements.
        :return: Total energy consumed.
        """

        torque = np.array(self.record['tau' + str(joint_number)])
        angular_velocity = np.array(self.record['qdot' + str(joint_number)])
        # Calculate instantaneous power (torque * angular velocity)
        power = torque * angular_velocity
        
        # Generate time series starting from 0
        time_series = np.arange(0, len(power) * time_interval, time_interval)
        
        # Calculate energy using the trapezoidal rule
        energy = np.trapz(power, time_series)
        return energy
    
    def extract_calculated_energy_all_joints(self, delta_time, num_joints=6):
        energy = {}
        for joint_number in range(1, num_joints + 1):
             temp = self.calculate_energy(joint_number, delta_time)
             energy[joint_number] = {'energy': temp}
        return energy

    def plot_JTS_data(self, joint_number, base_path, width=800, height=600):
        trace_actual = go.Scatter(
            x=self.record['t'],
            y=self.record['tau' + str(joint_number)],
            mode='lines',
            name='Actual torque'
        )
        trace_JTS = go.Scatter(
            x=self.record['t'],
            y=self.record['tauJts' + str(joint_number)],
            mode='lines',
            name='Sensor torque'
        )
        layout = go.Layout(
            title=f'Joint {joint_number} Sensor Value',
            xaxis=dict(
                title='Time (m)',
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            yaxis=dict(
                title='Joint Sensor Torque (Nm)',
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            margin=dict(l=40, r=40, t=40, b=40),
            width=width,
            height=height,
            plot_bgcolor='white',  # White background
            paper_bgcolor='white'
        )
        fig = go.Figure(data=[trace_actual, trace_JTS], layout=layout)
        iplot(fig)    

        # Generate file name based on joint number
        file_name = f'Joint_{joint_number}_Torque_Sensor_Plot.png'    
        # Save the plot as a PNG file at the specified base path
        full_path = os.path.join(base_path, file_name)
        fig.write_image(full_path) 

    def plot_nominal_vs_measured(self, base_path, width=800, height=600):
        trace_nominal = go.Scatter(
            x=self.record['t'],
            y=self.record['tauref1'],
            mode='lines',
            name='nominal motor position'
        )
        trace_actual = go.Scatter(
            x=self.record['t'],
            y=self.record['tauref4'],
            mode='lines',
            name='measured motor position'
        )

        layout = go.Layout(
            title=f'Motor Position Plot',
            xaxis=dict(
                title='Time (m)',
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            yaxis=dict(
                title='Motor Position (rad)',
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            margin=dict(l=40, r=40, t=40, b=40),
            width=width,
            height=height,
            plot_bgcolor='white',  # White background
            paper_bgcolor='white'
        )
        fig = go.Figure(data=[trace_nominal, trace_actual], layout=layout)
        iplot(fig)    

        # Generate file name based on joint number
        file_name = f'nominal_vs_measured_position_Plot.png'    
        # Save the plot as a PNG file at the specified base path
        full_path = os.path.join(base_path, file_name)
        fig.write_image(full_path) 

    def plot_desired_vs_measured(self, base_path, width=800, height=600):
        trace_desired = go.Scatter(
            x=self.record['t'],
            y=self.record['tauref2'],
            mode='lines',
            name='desired motor position'
        )
        trace_actual = go.Scatter(
            x=self.record['t'],
            y=self.record['tauref4'],
            mode='lines',
            name='measured motor position'
        )

        layout = go.Layout(
            title=f'Motor Position Plot',
            xaxis=dict(
                title='Time (m)',
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            yaxis=dict(
                title='Motor Position (rad)',
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            margin=dict(l=40, r=40, t=40, b=40),
            width=width,
            height=height,
            plot_bgcolor='white',  # White background
            paper_bgcolor='white'
        )
        fig = go.Figure(data=[trace_desired, trace_actual], layout=layout)
        iplot(fig)    

        # Generate file name based on joint number
        file_name = f'desired_vs_measured_position_Plot.png'    
        # Save the plot as a PNG file at the specified base path
        full_path = os.path.join(base_path, file_name)
        fig.write_image(full_path) 

    def plot_nominal_vs_measured_error(self, base_path, width=800, height=600):
        trace_nominal_error = go.Scatter(
            x=self.record['t'],
            y=[a - b for a, b in zip(self.record['tauref1'], self.record['tauref4'])],  # Difference across all elements
            mode='lines',
            name='nominal motor position'
        )

        layout = go.Layout(
            title=f'Nominal vs. Measured Error Plot',
            xaxis=dict(
                title='Time (m)',
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            yaxis=dict(
                title='Motor Position Error (rad)',
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            margin=dict(l=40, r=40, t=40, b=40),
            width=width,
            height=height,
            plot_bgcolor='white',  # White background
            paper_bgcolor='white'
        )
        fig = go.Figure(data=[trace_nominal_error], layout=layout)
        iplot(fig)    

        # Generate file name based on joint number
        file_name = f'Nominal_vs_measured_position_error_Plot.png'    
        # Save the plot as a PNG file at the specified base path
        full_path = os.path.join(base_path, file_name)
        fig.write_image(full_path) 



    def plot_desired_vs_measured_error(self, base_path, width=800, height=600):
        trace_desired_error = go.Scatter(
            x=self.record['t'],
             y=[a - b for a, b in zip(self.record['tauref2'], self.record['tauref4'])],  # Difference across all elements
            mode='lines',
            name='desired motor position'
        )

        layout = go.Layout(
            title=f'Desired vs. Measured Error Plot',
            xaxis=dict(
                title='Time (m)',
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            yaxis=dict(
                title='Motor Position (rad)',
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            margin=dict(l=40, r=40, t=40, b=40),
            width=width,
            height=height,
            plot_bgcolor='white',  # White background
            paper_bgcolor='white'
        )
        fig = go.Figure(data=[trace_desired_error], layout=layout)
        iplot(fig)    

        # Generate file name based on joint number
        file_name = f'desired_vs_measured_position_error_plot.png'    
        # Save the plot as a PNG file at the specified base path
        full_path = os.path.join(base_path, file_name)
        fig.write_image(full_path) 

    def plot_estimated_fric(self, joint_number, base_path, width=800, height=600):
        trace_actual = go.Scatter(
            x=self.record['t'],
            y=self.record['tauref' + str(joint_number)],
            mode='lines',
            name='estimated friction'
        )

        layout = go.Layout(
            title=f'Joint {joint_number} Estimated Friction',
            xaxis=dict(
                title='Time (m)',
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            yaxis=dict(
                title='Estimated Friction Torque (Nm)',
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            margin=dict(l=40, r=40, t=40, b=40),
            width=width,
            height=height,
            plot_bgcolor='white',  # White background
            paper_bgcolor='white'
        )
        fig = go.Figure(data=[trace_actual], layout=layout)
        iplot(fig)    

        # Generate file name based on joint number
        file_name = f'Joint_{joint_number}_Estimated_Friction_Torque_Plot.png'    
        # Save the plot as a PNG file at the specified base path
        full_path = os.path.join(base_path, file_name)
        fig.write_image(full_path) 

    def plot_tauPD(self, joint_number, base_path, width=800, height=600):
        trace_actual = go.Scatter(
            x=self.record['t'],
            y=self.record['tauidyn' + str(joint_number)],
            mode='lines',
            name='PD torque'
        )

        layout = go.Layout(
            title=f'Joint {joint_number} Estimated Friction',
            xaxis=dict(
                title='Time (m)',
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            yaxis=dict(
                title='PD Torque (Nm)',
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            margin=dict(l=40, r=40, t=40, b=40),
            width=width,
            height=height,
            plot_bgcolor='white',  # White background
            paper_bgcolor='white'
        )
        fig = go.Figure(data=[trace_actual], layout=layout)
        iplot(fig)    

        # Generate file name based on joint number
        file_name = f'Joint_{joint_number}_PD_Torque_Plot.png'    
        # Save the plot as a PNG file at the specified base path
        full_path = os.path.join(base_path, file_name)
        fig.write_image(full_path) 

    def plot_JTS_Raw_data(self, joint_number, base_path, width=800, height=600):
        trace_raw1 = go.Scatter(
            x=self.record['t'],
            y=self.record['tauJtsRaw1' + str(joint_number)],
            mode='lines',
            name='Raw data 1'
        )
        trace_raw2 = go.Scatter(
            x=self.record['t'],
            y=self.record['tauJtsRaw2' + str(joint_number)],
            mode='lines',
            name='Raw data 2'
        )
        layout = go.Layout(
            title=f'Joint {joint_number} Torque Sensor Value',
            xaxis=dict(
                title='Time (m)',
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            yaxis=dict(
                title='Joint Torque Sensor  Raw data(mV)',
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            margin=dict(l=40, r=40, t=40, b=40),
            width=width,
            height=height,
            plot_bgcolor='white',  # White background
            paper_bgcolor='white'
        )
        fig = go.Figure(data=[trace_raw1, trace_raw2], layout=layout)
        iplot(fig)    

        # Generate file name based on joint number
        file_name = f'Joint_{joint_number}_Torque_Sensor_Raw_Plot.png'    
        # Save the plot as a PNG file at the specified base path
        full_path = os.path.join(base_path, file_name)
        fig.write_image(full_path) 

    def plot_JTS_Raw_data_avg(self, joint_number, base_path, width=800, height=600):
        trace_raw1 = go.Scatter(
            x=self.record['t'],
            y=0.5*(np.array(self.record['tauJtsRaw1' + str(joint_number)]) + np.array(self.record['tauJtsRaw1' + str(joint_number)])),
            mode='lines',
            name='Raw data 1'
        )
        # trace_raw2 = go.Scatter(
        #     x=self.record['t'],
        #     y=self.record['tauJtsRaw2' + str(joint_number)],
        #     mode='lines',
        #     name='Raw data 2'
        # )
        layout = go.Layout(
            title=f'Joint {joint_number} Torque Sensor Value',
            xaxis=dict(
                title='Time (m)',
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            yaxis=dict(
                title='Joint Torque Sensor  Raw data(mV)',
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            margin=dict(l=40, r=40, t=40, b=40),
            width=width,
            height=height,
            plot_bgcolor='white',  # White background
            paper_bgcolor='white'
        )
        fig = go.Figure(data=[trace_raw1], layout=layout)
        iplot(fig)    

        # Generate file name based on joint number
        file_name = f'Joint_{joint_number}_Torque_Sensor_Raw_Plot.png'    
        # Save the plot as a PNG file at the specified base path
        full_path = os.path.join(base_path, file_name)
        fig.write_image(full_path) 

    def plot_robot_and_desired_path(self, joint_number, base_path, showPlot=True, width=800, height=600):
        trace_actual = go.Scatter(
            x=self.record['t'],
            y=self.record['qd' + str(joint_number)],
            mode='lines+markers',

            name='Desired Path'
        )
        trace_desired = go.Scatter(
            x=self.record['t'],
            y=self.record['q' + str(joint_number)],
            mode='lines',
            name='Actual Path',
            line=dict(dash='dash')
        )
        layout = go.Layout(
            title=f'Joint {joint_number} Pose Tracking',
            xaxis=dict(
                title='Time (m)',
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            yaxis=dict(
                title='Joint Pose (rad)',
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            margin=dict(l=40, r=40, t=40, b=40),
            width=width,
            height=height,
            plot_bgcolor='white',  # White background
            paper_bgcolor='white'
        )
        fig = go.Figure(data=[trace_actual, trace_desired], layout=layout)
        if(showPlot):
            iplot(fig)   
         

        # Generate file name based on joint number
        file_name = f'Joint_{joint_number}_Pose_Tracking.png'    
        # Save the plot as a PNG file at the specified base path
        full_path = os.path.join(base_path, file_name)
        fig.write_image(full_path) 

                                    

    def plot_error_path(self, joint_number, base_path, width=600, height=400):
        errors = np.array(self.record['qe' + str(joint_number)])
        rms_error = np.sqrt(np.mean(errors**2))
        max_error = np.max(np.abs(errors))

        trace_error = go.Scatter(
            x=self.record['t'],
            y=errors,
            mode='lines',
            name=f'Error Joint {joint_number} [rad]',
            line=dict(width=4)  # Line thickness
        )

        # Using <span> with background color and text color (highlight) for values
        annotation_text = (
            f'RMS Error: <span style="color:red; font-weight:bold; background-color:yellow;">{rms_error:.6f}</span> rad, '
            f'Max Error: <span style="color:red; font-weight:bold; background-color:yellow;">{max_error:.6f}</span> rad'
        )

        annotations = [
            dict(
                xref='paper', yref='paper',
                x=0.5, y=1.05,
                xanchor='center', yanchor='top',
                # text=f'RMS Error: {rms_error:.6f} rad, Max Error: {max_error:.6f} rad',
                text=annotation_text,
                font=dict(family='Arial', size=16, color='red'),
                showarrow=False,
                bgcolor='white',         # White background for the annotation
                bordercolor='#D3D3D3',     # Border color for the annotation
                borderwidth=2            # Border width for the annotation
            )
        ]

        layout = go.Layout(
            title=f'Joint {joint_number} Pose Tracking Error',
            xaxis=dict(
                title='Time (s)',
                gridcolor='#D3D3D3',  # Light gray grid lines for x-axis
                gridwidth=1,
                griddash='dash',  # Dashed grid lines
                showline=True,      # These lines
                linewidth=1,       # and these settings add the box
                linecolor='#D3D3D3', # around the plot
                mirror=True        # Reflects the axis line on the opposite side
            ),
            yaxis=dict(
                title='Error (rad)',
                gridcolor='#D3D3D3',  # Light gray grid lines for y-axis
                gridwidth=1,
                griddash='dash',
                showline=True,      # These lines
                linewidth=1,       # and these settings add the box
                linecolor='#D3D3D3', # around the plot
                mirror=True        # Reflects the axis line on the opposite side
            ),
            annotations=annotations,
            margin=dict(l=40, r=40, t=40, b=40),
            width=width,
            height=height,
            plot_bgcolor='white',  # White background
            paper_bgcolor='white'
        )

        fig = go.Figure(data=[trace_error], layout=layout)
        # iplot(fig)

        # Generate file name based on joint number
        file_name = f'Joint_{joint_number}_Pose_Tracking_Error.png'    
        # Save the plot as a PNG file at the specified base path
        full_path = os.path.join(base_path, file_name)
        fig.write_image(full_path) 

        return rms_error, max_error
    
    def extract_errors_for_all_joints(self, base_path, num_joints=6):
        errors = {}
        for joint_number in range(1, num_joints + 1):
            rms_error, max_error = self.plot_error_path(joint_number, base_path)
            errors[joint_number] = {'RMS Error': rms_error, 'Max Error': max_error}
        return errors
    

    
    def generate_report(self, errors, report_path):
        with open(report_path, 'w') as file:
            file.write('Joint Number, RMS Error (rad), Max Error (rad)\n')
            for joint, error_values in errors.items():
                file.write(f'{joint}, {error_values["RMS Error"]:.6f}, {error_values["Max Error"]:.6f}\n')
                
    def create_table(self, df, title):
        # Title for the table
        styles = getSampleStyleSheet()
        title = Paragraph(title, styles['Heading2'])

        # Convert DataFrame to a list of lists for ReportLab Table
        data = [df.columns.to_list()] + df.values.tolist()
        table = Table(data)

        # Add style to the table
        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ])
        table.setStyle(style)

        return [title, Spacer(1, 12), table]
    
    def generate_pdf_report(self, position_errors, velocity_errors, pdf_path):
        # Create DataFrames
        df_pos = pd.DataFrame(position_errors).T
        df_vel = pd.DataFrame(velocity_errors).T

        # Format the DataFrames
        for df in [df_pos, df_vel]:
            df.index.name = 'Joint Number'
            df.reset_index(inplace=True)
            df['Joint Number'] = df['Joint Number'].astype(int)
            df['RMS Error'] = df['RMS Error'].apply(lambda x: f'{x:.3e}')
            df['Max Error'] = df['Max Error'].apply(lambda x: f'{x:.3e}')
            df.columns = ['Joint Number', 'RMS Error', 'Max Error']

        # Create tables with titles
        df_pos.columns = ['Joint Number', 'RMS Error (rad)', 'Max Error (rad)']    
        df_vel.columns = ['Joint Number', 'RMS Error (rad/s)', 'Max Error (rad/s)']   
        elements = self.create_table(df_pos, "Position Tracking Errors") + [Spacer(1, 24)] \
                + self.create_table(df_vel, "Velocity Tracking Errors")

        # Create a PDF document
        pdf = SimpleDocTemplate(pdf_path, pagesize=letter)
        
        # Build the PDF
        pdf.build(elements)

    def generate_pdf_report_with_energy(self, position_errors, velocity_errors, energy, pdf_path):
        # Create DataFrames
        df_pos = pd.DataFrame(position_errors).T
        df_vel = pd.DataFrame(velocity_errors).T
        df_energy = pd.DataFrame(energy).T

        # Format the DataFrames
        for df in [df_pos, df_vel]:
            df.index.name = 'Joint Number'
            df.reset_index(inplace=True)
            df['Joint Number'] = df['Joint Number'].astype(int)
            df['RMS Error'] = df['RMS Error'].apply(lambda x: f'{x:.3e}')
            df['Max Error'] = df['Max Error'].apply(lambda x: f'{x:.3e}')
            df.columns = ['Joint Number', 'RMS Error', 'Max Error']

        df_energy.index.name = 'Joint Number'
        df_energy.reset_index(inplace=True)
        df_energy['Joint Number'] = df_energy['Joint Number'].astype(int)    
        df_energy['energy'] = df_energy['energy'].apply(lambda x: f'{x:.3e}')
        # Create tables with titles
        df_pos.columns = ['Joint Number', 'RMS Error (rad)', 'Max Error (rad)']    
        df_vel.columns = ['Joint Number', 'RMS Error (rad/s)', 'Max Error (rad/s)']  
        df_energy.columns = ['Joint Number', 'Total Energy Consumed (Joules)'] 
        elements = self.create_table(df_pos, "Position Tracking Errors") + [Spacer(1, 24)] \
                + self.create_table(df_vel, "Velocity Tracking Errors") + [Spacer(1, 24)] \
                + self.create_table(df_energy, "Total Energy Consumption")

        # Create a PDF document
        pdf = SimpleDocTemplate(pdf_path, pagesize=letter)
        
        # Build the PDF
        pdf.build(elements)

    def generate_pdf_report_with_energy(self, position_errors, velocity_errors, energy, joint_gain, pdf_path):
        # Create DataFrames
        df_pos = pd.DataFrame(position_errors).T
        df_vel = pd.DataFrame(velocity_errors).T
        df_energy = pd.DataFrame(energy).T
        df_gains = pd.DataFrame(joint_gain)

        # Format the DataFrames
        for df in [df_pos, df_vel]:
            df.index.name = 'Joint Number'
            df.reset_index(inplace=True)
            df['Joint Number'] = df['Joint Number'].astype(int)
            df['RMS Error'] = df['RMS Error'].apply(lambda x: f'{x:.3e}')
            df['Max Error'] = df['Max Error'].apply(lambda x: f'{x:.3e}')
            df.columns = ['Joint Number', 'RMS Error', 'Max Error']

        df_energy.index.name = 'Joint Number'
        df_energy.reset_index(inplace=True)
        df_energy['Joint Number'] = df_energy['Joint Number'].astype(int)    
        df_energy['energy'] = df_energy['energy'].apply(lambda x: f'{x:.3e}')

        df_gains.index.name = 'Joint Number'
        df_gains.reset_index(inplace=True)
        df_gains['Joint Number'] = df_gains['Joint Number'] + 1
        df_gains['Joint Number'] = df_gains['Joint Number'].astype(int)    

        df_gains.columns = ['Joint Number', 'Kp', 'Kv', 'KL2']
        # Create tables with titles
        df_pos.columns = ['Joint Number', 'RMS Error (rad)', 'Max Error (rad)']    
        df_vel.columns = ['Joint Number', 'RMS Error (rad/s)', 'Max Error (rad/s)']  
        df_energy.columns = ['Joint Number', 'Total Energy Consumed (Joules)'] 
        elements = self.create_table(df_pos, "Position Tracking Errors") + [Spacer(1, 24)] \
                + self.create_table(df_vel, "Velocity Tracking Errors") + [Spacer(1, 24)] \
                + self.create_table(df_energy, "Total Energy Consumption") + [Spacer(1, 40)] \
                + self.create_table(df_gains, "Joint Control Gains")

        # Create a PDF document
        pdf = SimpleDocTemplate(pdf_path, pagesize=letter)
        
        # Build the PDF
        pdf.build(elements)     

    def generate_pdf_report_task_control_mod_image(self, translation_errors, rotation_errors, joint_gain, test_info, pdf_path, image_path):
        # Extracting information from the test_info dictionary
        robot_name = test_info.get("robot_name", "Unknown Robot")
        payload = test_info.get("payload", "N/A")
        test_velocity = test_info.get("test_velocity", "N/A")
        test_acceleration = test_info.get("test_acceleration", "N/A")
        # Introductory information
        styles = getSampleStyleSheet()
        title = Paragraph("Robot Control Performance Report", styles['Title'])
        robot_info = Paragraph(f"<b>Robot:</b> {robot_name}", styles['BodyText'])
        payload_info = Paragraph(f"<b>Payload:</b> {payload} kg", styles['BodyText'])
        velocity_info = Paragraph(f"<b>Velocity level:</b> {test_velocity} %", styles['BodyText'])
        acceleration_info = Paragraph(f"<b>Acceleration level:</b> {test_acceleration} %", styles['BodyText'])
        # Create DataFrames
        # df_pos = pd.DataFrame(translation_errors).T
        # df_vel = pd.DataFrame(rotation_errors).T
         # Create a general title for the page
        # Convert translation errors from meters to millimeters
        formatted_translation_errors = [
            [axis, rms * 1000, max_err * 1000] for axis, rms, max_err in translation_errors
        ]

        # page_title = Paragraph("Control Performance Report", styles['Title'])
        formatted_translation_errors = [[axis, f'{rms:.3e}', f'{max_err:.3e}'] for axis, rms, max_err in formatted_translation_errors]
        formatted_rotation_errors = [[axis, f'{rms:.3e}', f'{max_err:.3e}'] for axis, rms, max_err in rotation_errors]
        # df_translation = pd.DataFrame(formatted_translation_errors).T
        # df_rotation = pd.DataFrame(formatted_rotation_errors).T
        df_gains = pd.DataFrame(joint_gain)

        # df_translation['RMS Error'] = df_translation['RMS Error'].apply(lambda x: f'{x:.3e}')
        # df_rotation['Max Error'] = df_rotation['Max Error'].apply(lambda x: f'{x:.3e}')
        # Create DataFrames
        df_translation = pd.DataFrame(formatted_translation_errors, columns=['Axis', 'RMS Error (mm)', 'Max Error (mm)'])
        df_rotation = pd.DataFrame(formatted_rotation_errors, columns=['Axis', 'RMS Error (°)', 'Max Error (°)'])
        
        # df_translation.index.name = 'Axis'
        # df_translation.reset_index(inplace=True)
        # df_translation
        # df_translation.columns = ['Axis', 'RMS Error (mm)', 'Max Error (mm)']

        # df_rotation.index.name = 'Axis'
        # df_rotation.reset_index(inplace=True)
        # df_rotation.columns = ['Axis', 'RMS Error (°)', 'Max Error (°)']

        df_gains.index.name = 'Joint Number'
        df_gains.reset_index(inplace=True)
        df_gains['Joint Number'] = df_gains['Joint Number'] + 1
        df_gains['Joint Number'] = df_gains['Joint Number'].astype(int)  
        df_gains.columns = ['Joint Number', 'Kp', 'Kv', 'KL2'] 


         # Create tables with titles
        # elements = [page_title, Spacer(1, 15)]
        elements = [title, Spacer(1, 12), robot_info, Spacer(1, 10), payload_info, Spacer(1, 10), velocity_info, Spacer(1, 10), acceleration_info, Spacer(1, 20)]
        elements += self.create_table(df_translation, "Task Space Motion: Translation Errors") + [Spacer(1, 20)]
        elements += self.create_table(df_rotation, "Task Space Motion: Rotation Errors") + [Spacer(1, 20)]
        elements += self.create_table(df_gains, "Task Control Gains")

        # Insert a page break here
        elements.append(PageBreak())

        # Add first three images
        for img_path in image_path[:2]:
            elements.append(Image(img_path, width=500, height=300))  # Adjust width and height as needed
            elements.append(Spacer(1, 15))

        # Insert another page break for the next set of images
        elements.append(PageBreak())

           # Add the next three images
        for img_path in image_path[2:4]:
            elements.append(Image(img_path, width=500, height=300))  # Adjust width and height as needed
            elements.append(Spacer(1, 15))

        # Create a PDF document
        pdf = SimpleDocTemplate(pdf_path, pagesize=letter)
        pdf.build(elements)   

    def generate_pdf_report_with_energy_image(self, position_errors, velocity_errors, energy, joint_gain, test_info, pdf_path, image_path):
        styles = getSampleStyleSheet()

        # Extracting information from the test_info dictionary
        robot_name = test_info.get("robot_name", "Unknown Robot")
        payload = test_info.get("payload", "N/A")
        test_velocity = test_info.get("test_velocity", "N/A")
        test_acceleration = test_info.get("test_acceleration", "N/A")
        # Introductory information
        title = Paragraph("Robot Control Performance Report", styles['Title'])
        robot_info = Paragraph(f"<b>Robot:</b> {robot_name}", styles['BodyText'])
        payload_info = Paragraph(f"<b>Payload:</b> {payload} kg", styles['BodyText'])
        velocity_info = Paragraph(f"<b>Velocity level:</b> {test_velocity} %", styles['BodyText'])
        acceleration_info = Paragraph(f"<b>Acceleration level:</b> {test_acceleration} %", styles['BodyText'])

        # Create DataFrames
        df_pos = pd.DataFrame(position_errors).T
        df_vel = pd.DataFrame(velocity_errors).T
        df_energy = pd.DataFrame(energy).T
        df_gains = pd.DataFrame(joint_gain)

        rad_to_deg = lambda rad: rad * (180 / math.pi)
        df_pos['RMS Error (deg)'] = df_pos['RMS Error'].apply(rad_to_deg)
        df_pos['Max Error (deg)'] = df_pos['Max Error'].apply(rad_to_deg)
        df_vel['RMS Error (deg/s)'] = df_vel['RMS Error'].apply(rad_to_deg)
        df_vel['Max Error (deg/s)'] = df_vel['Max Error'].apply(rad_to_deg)

        # Format the DataFrames
        for df in [df_pos, df_vel]:
            df.index.name = 'Joint Number'
            df.reset_index(inplace=True)
            df['Joint Number'] = df['Joint Number'].astype(int)
            df['RMS Error'] = df['RMS Error'].apply(lambda x: f'{x:.3e}')
            df['Max Error'] = df['Max Error'].apply(lambda x: f'{x:.3e}')
            # df.columns = ['Joint Number', 'RMS Error', 'Max Error']

        df_pos['RMS Error (deg)'] = df_pos['RMS Error (deg)'].apply(lambda x: f'{x:.3e}')
        df_pos['Max Error (deg)'] = df_pos['Max Error (deg)'].apply(lambda x: f'{x:.3e}')
        df_vel['RMS Error (deg/s)'] = df_vel['RMS Error (deg/s)'].apply(lambda x: f'{x:.3e}')
        df_vel['Max Error (deg/s)'] = df_vel['Max Error (deg/s)'].apply(lambda x: f'{x:.3e}')

        df_energy.index.name = 'Joint Number'
        df_energy.reset_index(inplace=True)
        df_energy['Joint Number'] = df_energy['Joint Number'].astype(int)    
        df_energy['energy'] = df_energy['energy'].apply(lambda x: f'{x:.3e}')

        df_gains.index.name = 'Joint Number'
        df_gains.reset_index(inplace=True)
        df_gains['Joint Number'] = df_gains['Joint Number'] + 1
        df_gains['Joint Number'] = df_gains['Joint Number'].astype(int)    

        df_gains.columns = ['Joint Number', 'Kp', 'Kv', 'KL2']
        # Create tables with titles
        df_pos.columns = ['Joint Number', 'RMS Error (rad)', 'Max Error (rad)',  'RMS Error (deg)' ,'Max Error (deg)']    
        df_vel.columns = ['Joint Number', 'RMS Error (rad/s)',  'Max Error (rad/s)', 'RMS Error (deg/s)', 'Max Error (deg/s)']  
        df_energy.columns = ['Joint Number', 'Total Energy Consumed (Joules)'] 

        # Create a PDF document
        pdf = SimpleDocTemplate(pdf_path, pagesize=letter)

        # Build the PDF with the intro and tables
        elements = [title, Spacer(1, 12), robot_info, Spacer(1, 12), payload_info, Spacer(1, 12), velocity_info, Spacer(1, 12), acceleration_info, Spacer(1, 24)]
        elements += self.create_table(df_pos, "Position Tracking Errors") + [Spacer(1, 24)]
        elements += self.create_table(df_vel, "Velocity Tracking Errors") + [Spacer(1, 24)]

        # Insert a page break here
        elements.append(PageBreak())

        elements += self.create_table(df_energy, "Total Energy Consumption") + [Spacer(1, 24)]
        elements += self.create_table(df_gains, "Joint Control Gains")

        # Insert a page break here
        elements.append(PageBreak())

        # Add first three images
        for img_path in image_path[:2]:
            elements.append(Image(img_path, width=500, height=300))  # Adjust width and height as needed
            elements.append(Spacer(1, 10))

        # Insert another page break for the next set of images
        elements.append(PageBreak())

           # Add the next three images
        for img_path in image_path[2:4]:
            elements.append(Image(img_path, width=500, height=300))  # Adjust width and height as needed
            elements.append(Spacer(1, 10))

        # Insert another page break for the next set of images
        elements.append(PageBreak())

           # Add the next three images
        for img_path in image_path[4:]:
            elements.append(Image(img_path, width=500, height=300))  # Adjust width and height as needed
            elements.append(Spacer(1, 10))
        

        pdf.build(elements)  

    def generate_pdf_report_with_energy(self, position_errors, velocity_errors, energy, joint_gain, payload, test_velocity, test_acceleration, pdf_path):
            styles = getSampleStyleSheet()

            # Introductory information
            title = Paragraph("Robot Control Performance Report", styles['Title'])
            payload_info = Paragraph(f"<b>Payload:</b> {payload} kg", styles['BodyText'])
            velocity_info = Paragraph(f"<b>Velocity level:</b> {test_velocity} %", styles['BodyText'])
            acceleration_info = Paragraph(f"<b>Acceleration level:</b> {test_acceleration} %", styles['BodyText'])

            # Create DataFrames
            df_pos = pd.DataFrame(position_errors).T
            df_vel = pd.DataFrame(velocity_errors).T
            df_energy = pd.DataFrame(energy).T
            df_gains = pd.DataFrame(joint_gain)

            rad_to_deg = lambda rad: rad * (180 / math.pi)
            df_pos['RMS Error (deg)'] = df_pos['RMS Error'].apply(rad_to_deg)
            df_pos['Max Error (deg)'] = df_pos['Max Error'].apply(rad_to_deg)
            df_vel['RMS Error (deg/s)'] = df_vel['RMS Error'].apply(rad_to_deg)
            df_vel['Max Error (deg/s)'] = df_vel['Max Error'].apply(rad_to_deg)

            # Format the DataFrames
            for df in [df_pos, df_vel]:
                df.index.name = 'Joint Number'
                df.reset_index(inplace=True)
                df['Joint Number'] = df['Joint Number'].astype(int)
                df['RMS Error'] = df['RMS Error'].apply(lambda x: f'{x:.3e}')
                df['Max Error'] = df['Max Error'].apply(lambda x: f'{x:.3e}')
                # df.columns = ['Joint Number', 'RMS Error', 'Max Error']

            df_pos['RMS Error (deg)'] = df_pos['RMS Error (deg)'].apply(lambda x: f'{x:.3e}')
            df_pos['Max Error (deg)'] = df_pos['Max Error (deg)'].apply(lambda x: f'{x:.3e}')
            df_vel['RMS Error (deg/s)'] = df_vel['RMS Error (deg/s)'].apply(lambda x: f'{x:.3e}')
            df_vel['Max Error (deg/s)'] = df_vel['Max Error (deg/s)'].apply(lambda x: f'{x:.3e}')

            df_energy.index.name = 'Joint Number'
            df_energy.reset_index(inplace=True)
            df_energy['Joint Number'] = df_energy['Joint Number'].astype(int)    
            df_energy['energy'] = df_energy['energy'].apply(lambda x: f'{x:.3e}')

            df_gains.index.name = 'Joint Number'
            df_gains.reset_index(inplace=True)
            df_gains['Joint Number'] = df_gains['Joint Number'] + 1
            df_gains['Joint Number'] = df_gains['Joint Number'].astype(int)    

            df_gains.columns = ['Joint Number', 'Kp', 'Kv', 'KL2']
            # Create tables with titles
            df_pos.columns = ['Joint Number', 'RMS Error (rad)', 'Max Error (rad)',  'RMS Error (deg)' ,'Max Error (deg)']    
            df_vel.columns = ['Joint Number', 'RMS Error (rad/s)',  'Max Error (rad/s)', 'RMS Error (deg/s)', 'Max Error (deg/s)']  
            df_energy.columns = ['Joint Number', 'Total Energy Consumed (Joules)'] 

            # Create a PDF document
            pdf = SimpleDocTemplate(pdf_path, pagesize=letter)

            # Build the PDF with the intro and tables
            elements = [title, Spacer(1, 12), payload_info, Spacer(1, 12), velocity_info, Spacer(1, 12), acceleration_info, Spacer(1, 24)]
            elements += self.create_table(df_pos, "Position Tracking Errors") + [Spacer(1, 24)]
            elements += self.create_table(df_vel, "Velocity Tracking Errors") + [Spacer(1, 24)]

            # Insert a page break here
            elements.append(PageBreak())

            elements += self.create_table(df_energy, "Total Energy Consumption") + [Spacer(1, 24)]
            elements += self.create_table(df_gains, "Joint Control Gains")
            

            pdf.build(elements)                      

    def plot_robot_and_desired_velocity(self, joint_number,base_path, width=800, height=600):
        trace_actual = go.Scatter(
            x=self.record['t'],
            y=self.record['qdotd' + str(joint_number)],
            mode='lines+markers',
            name='Desired Velocity'
        )
        trace_desired = go.Scatter(
            x=self.record['t'],
            y=self.record['qdot' + str(joint_number)],
            mode='lines',
            name='Actual Velocity',
            line=dict(dash='dash')
        )
        layout = go.Layout(
            title=f'Joint {joint_number} Velocity Tracking',
            xaxis=dict(
                title='Time (s)',
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            yaxis=dict(
                title='Joint Pose (rad)',
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            margin=dict(l=40, r=40, t=40, b=40),
            width=width,
            height=height,
            plot_bgcolor='white',  # White background
            paper_bgcolor='white'
        )
        fig = go.Figure(data=[trace_actual, trace_desired], layout=layout)
        # iplot(fig)   

        # Generate file name based on joint number
        file_name = f'Joint_{joint_number}_Vel_Tracking.png'    
        # Save the plot as a PNG file at the specified base path
        full_path = os.path.join(base_path, file_name)
        fig.write_image(full_path)     

    def plot_task_motion_2D(self, plot_axis, base_path, width=800, height=600):
        def extend_range(min_val, max_val, extension=0.008):
            return (min_val - extension, max_val + extension)

        if (plot_axis == "XY"):
            
            trace_actual = go.Scatter(
            x=self.record['pd1'],
            y=self.record['pd2'],
            mode='lines',
            name='Desired path',
            line=dict(color='black')
            )
            trace_desired = go.Scatter(
                x=self.record['p1'],
                y=self.record['p2'],
                mode='lines',
                name='Actual path',
                line=dict(dash='dash', color='red')
            )
            x_range = extend_range(min(self.record['p1'] + self.record['pd1']), max(self.record['p1'] + self.record['pd1']))
            y_range = extend_range(min(self.record['p2'] + self.record['pd2']), max(self.record['p2'] + self.record['pd2']))
            xtitle = "X-axis (m)"
            ytitle = "Y-axis (m)"
        elif (plot_axis == "YZ"):
            trace_actual = go.Scatter(
            x=self.record['pd2'],
            y=self.record['pd3'],
            mode='lines',
            name='Desired path',
            line=dict(color='black')
            )
            trace_desired = go.Scatter(
                x=self.record['p2'],
                y=self.record['p3'],
                mode='lines',
                name='Actual path',
                line=dict(dash='dash', color='red')
            )   
            x_range = extend_range(min(self.record['p2'] + self.record['pd2']), max(self.record['p2'] + self.record['pd2']))
            y_range = extend_range(min(self.record['p3'] + self.record['pd3']), max(self.record['p3'] + self.record['pd3']))            
            xtitle = "Y-axis (m)"
            ytitle = "Z-axis (m)"                 
        elif (plot_axis == "XZ"):
            trace_actual = go.Scatter(
            x=self.record['pd1'],
            y=self.record['pd3'],
            mode='lines',
            name='Desired path',
            line=dict(color='black')
            )
            trace_desired = go.Scatter(
                x=self.record['p1'],
                y=self.record['p3'],
                mode='lines',
                name='Actual path',
                line=dict(dash='dash', color='red')
            )
            x_range = extend_range(min(self.record['p1'] + self.record['pd1']), max(self.record['p1'] + self.record['pd1']))
            y_range = extend_range(min(self.record['p3'] + self.record['pd3']), max(self.record['p3'] + self.record['pd3']))            
            xtitle = "X-axis (m)"
            ytitle = "Z-axis (m)"            
        else:
            trace_actual = go.Scatter(
            x=self.record['pd1'],
            y=self.record['pd2'],
            mode='lines',
            name='Desired path',
            line=dict(color='black')
            )
            trace_desired = go.Scatter(
                x=self.record['p1'],
                y=self.record['p2'],
                mode='lines',
                name='Actual path',
                line=dict(dash='dash', color='red')
            )  
            x_range = extend_range(min(self.record['p1'] + self.record['pd1']), max(self.record['p1'] + self.record['pd1']))
            y_range = extend_range(min(self.record['p2'] + self.record['pd2']), max(self.record['p2'] + self.record['pd2']))              
            xtitle = "X-axis (m)"
            ytitle = "Y-axis (m)"             

        layout = go.Layout(
            # title=f'Task {joint_number} Velocity Tracking',
            title=f'Task Space Tracking',
            xaxis=dict(
                title= xtitle,
                range=x_range,
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            yaxis=dict(
                title= ytitle,
                range=y_range,
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            margin=dict(l=40, r=40, t=40, b=40),
            width=width,
            height=height,
            plot_bgcolor='white',  # White background
            paper_bgcolor='white'
        )

        fig = go.Figure(data=[trace_actual, trace_desired], layout=layout)
        # iplot(fig)   

        # Generate file name based on joint number
        file_name = f'Task Space Tracking {plot_axis}.png'    
        # Save the plot as a PNG file at the specified base path
        full_path = os.path.join(base_path, file_name)
        fig.write_image(full_path)   


    def plot_task_motion_3D(self, base_path, width=800, height=600):
        # Function to ensure minimum range
        # def ensure_min_range(min_val, max_val, min_range=0.1):
        #     current_range = max_val - min_val
        #     if current_range < min_range:
        #         extend = (min_range - current_range) / 2
        #         return (min_val - extend, max_val + extend)
        #     else:
        #         return (min_val, max_val)

        # # Calculate ranges for x, y, and z
        # x_range = ensure_min_range(min(self.record['p1'] + self.record['pd1']), max(self.record['p1'] + self.record['pd1']))
        # y_range = ensure_min_range(min(self.record['p2'] + self.record['pd2']), max(self.record['p2'] + self.record['pd2']))
        # z_range = ensure_min_range(min(self.record['p3'] + self.record['pd3']), max(self.record['p3'] + self.record['pd3']))
            # Function to extend range
        def extend_range(min_val, max_val, extension=0.01):
            return (min_val - extension, max_val + extension)

        # Calculate extended ranges for x, y, and z
        x_range = extend_range(min(self.record['p1'] + self.record['pd1']), max(self.record['p1'] + self.record['pd1']))
        y_range = extend_range(min(self.record['p2'] + self.record['pd2']), max(self.record['p2'] + self.record['pd2']))
        z_range = extend_range(min(self.record['p3'] + self.record['pd3']), max(self.record['p3'] + self.record['pd3']))

        trace_actual = go.Scatter3d(
            x=self.record['pd1'],
            y=self.record['pd2'],
            z=self.record['pd3'],
            mode='lines',
            name='Desired path',
            # marker=dict(size=4, color='black'),  # Set marker color
            line=dict(color='black', width=4)  # Set line color to black
        )
        trace_desired = go.Scatter3d(
            x=self.record['p1'],
            y=self.record['p2'],
            z=self.record['p3'],
            mode='lines',
            name='Actual path',
            line=dict(dash='dash', color='red', width=4)  # Set line color to red and dash style
        )

        layout = go.Layout(
            title='Task Space Tracking 3D',
            scene=dict(
                xaxis=dict(
                    title='X-axis (m)', 
                    range=x_range, 
                    backgroundcolor='white',  # White background
                    gridcolor='lightgrey',  # Light grey gridlines
                    gridwidth=1
                 ),
                yaxis=dict(
                    title='Y-axis (m)', 
                    range=y_range, 
                    backgroundcolor='white', 
                    gridcolor='lightgrey', 
                    gridwidth=1
                ),
                zaxis=dict(
                    title='Z-axis (m)', 
                    range=z_range, 
                    backgroundcolor='white', 
                    gridcolor='lightgrey', 
                    gridwidth=1
                ),
                # Define the camera position and view angle
                camera=dict(
                    eye=dict(x=2, y=2, z=0.5)  # Adjust the x, y, z values for a suitable view
                ),
                # Adding the box for better visualization
                aspectmode='cube'  # Bounding box will take shape of cube to enclose the data
            ),
            margin=dict(l=40, r=40, t=40, b=40),
            width=width,
            height=height,
            plot_bgcolor='white',  # White background
            paper_bgcolor='white'
        )

        fig = go.Figure(data=[trace_actual, trace_desired], layout=layout)
        # iplot(fig)

        # Generate file name
        file_name = 'Task_Space_Tracking_3D.png'
        # Save the plot as a PNG file at the specified base path
        full_path = os.path.join(base_path, file_name)
        fig.write_image(full_path)

        
    def plot_error_velocity(self, joint_number,base_path, width=600, height=400):
        errors = np.array(self.record['qdote' + str(joint_number)])
        rms_error = np.sqrt(np.mean(errors**2))
        max_error = np.max(np.abs(errors))

        trace_error = go.Scatter(
            x=self.record['t'],
            y=errors,
            mode='lines',
            name=f'Error Joint {joint_number} [rad/s]',
            line=dict(width=4)  # Line thickness
        )

        # Using <span> with background color and text color (highlight) for values
        annotation_text = (
            f'RMS Error: <span style="color:red; font-weight:bold; background-color:yellow;">{rms_error:.6f}</span> rad/s, '
            f'Max Error: <span style="color:red; font-weight:bold; background-color:yellow;">{max_error:.6f}</span> rad/s'
        )

        annotations = [
            dict(
                xref='paper', yref='paper',
                x=0.5, y=1.05,
                xanchor='center', yanchor='top',
                # text=f'RMS Error: {rms_error:.6f} rad, Max Error: {max_error:.6f} rad',
                text=annotation_text,
                font=dict(family='Arial', size=16, color='red'),
                showarrow=False,
                bgcolor='white',         # White background for the annotation
                bordercolor='#D3D3D3',     # Border color for the annotation
                borderwidth=2            # Border width for the annotation
            )
        ]

        layout = go.Layout(
            title=f'Joint {joint_number} Velocity Tracking Error',
            xaxis=dict(
                title='Time (s)',
                gridcolor='#D3D3D3',  # Light gray grid lines for x-axis
                gridwidth=1,
                griddash='dash',  # Dashed grid lines
                showline=True,      # These lines
                linewidth=1,       # and these settings add the box
                linecolor='#D3D3D3', # around the plot
                mirror=True        # Reflects the axis line on the opposite side
            ),
            yaxis=dict(
                title='Error (rad/s)',
                gridcolor='#D3D3D3',  # Light gray grid lines for y-axis
                gridwidth=1,
                griddash='dash',
                showline=True,      # These lines
                linewidth=1,       # and these settings add the box
                linecolor='#D3D3D3', # around the plot
                mirror=True        # Reflects the axis line on the opposite side
            ),
            annotations=annotations,
            margin=dict(l=40, r=40, t=40, b=40),
            width=width,
            height=height,
            plot_bgcolor='white',  # White background
            paper_bgcolor='white'
        )

        fig = go.Figure(data=[trace_error], layout=layout)
        # iplot(fig)

        # Generate file name based on joint number
        file_name = f'Joint_{joint_number}_Vel_Tracking_Error.png'    
        # Save the plot as a PNG file at the specified base path
        full_path = os.path.join(base_path, file_name)
        fig.write_image(full_path) 

        return rms_error, max_error

    def extract_vel_errors_for_all_joints(self, base_path, num_joints=6):
        errors = {}
        for joint_number in range(1, num_joints + 1):
            rms_error, max_error = self.plot_error_velocity(joint_number, base_path)
            errors[joint_number] = {'RMS Error': rms_error, 'Max Error': max_error}
        return errors

        

    def butter_lowpass(self, cutoff, fs, order=5):
        nyq = 0.5 * fs
        normal_cutoff = cutoff / nyq
        b, a = butter(order, normal_cutoff, btype='low', analog=False)
        return b, a

    def lowpass_filter(self, data, cutoff, fs=2000.0, order=5):
        b, a = self.butter_lowpass(cutoff, fs, order=order)
        y = lfilter(b, a, data)
        return y

        # # Example usage
        # if __name__ == "__main__":
        #     # Example data: A signal with a sampling rate of 100 Hz
        #     fs = 100.0  # Sampling rate
        #     cutoff = 10.0  # Desired cutoff frequency of the filter, Hz

        #     # Generate an example signal: a sine wave of frequency 5 Hz + a sine wave of frequency 50 Hz
        #     t = np.linspace(0, 1, int(fs), endpoint=False)
        #     data = np.sin(2 * np.pi * 5 * t) + np.sin(2 * np.pi * 50 * t)  # 5 Hz and 50 Hz components

        #     # Filter the data
        #     filtered_data = lowpass_filter(data, cutoff, fs)

        #     # filtered_data is the output array

    def plot_torque_report_filtered(self, joint_number, base_path, plotShow=True, cutoff=20.0, width=800, height=600):
        trace_actual = go.Scatter(
            x=self.record['t'],
            y=self.lowpass_filter(data=self.record['tau' + str(joint_number)], cutoff=cutoff),
            mode='lines',
            name='tauAct'
        )
        layout = go.Layout(
            title=f'Joint {joint_number} Torque',
            xaxis=dict(
                title='Time (m)',
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            yaxis=dict(
                title='Joint torque (Nm)',
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            margin=dict(l=40, r=40, t=40, b=40),
            width=width,
            height=height,
            plot_bgcolor='white',  # White background
            paper_bgcolor='white'
        )
        fig = go.Figure(data=[trace_actual], layout=layout)
        if(plotShow):
            iplot(fig)
        # iplot(fig)    

        # Generate file name based on joint number
        file_name = f'Joint_{joint_number}_Torque.png'    
        # Save the plot as a PNG file at the specified base path
        full_path = os.path.join(base_path, file_name)
        fig.write_image(full_path) 

    def plot_torque_report(self, joint_number, base_path, plotShow=True, width=800, height=600):
        trace_actual = go.Scatter(
            x=self.record['t'],
            y=self.record['tau' + str(joint_number)],
            mode='lines',
            name='tauAct'
        )
        layout = go.Layout(
            title=f'Joint {joint_number} Torque',
            xaxis=dict(
                title='Time (m)',
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            yaxis=dict(
                title='Joint torque (Nm)',
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            margin=dict(l=40, r=40, t=40, b=40),
            width=width,
            height=height,
            plot_bgcolor='white',  # White background
            paper_bgcolor='white'
        )
        fig = go.Figure(data=[trace_actual], layout=layout)
        if(plotShow):
            iplot(fig)
        # iplot(fig)    

        # Generate file name based on joint number
        file_name = f'Joint_{joint_number}_Torque.png'    
        # Save the plot as a PNG file at the specified base path
        full_path = os.path.join(base_path, file_name)
        fig.write_image(full_path) 

    def plot_torque_friction(self, joint_number, base_path, plotShow=True, width=800, height=600):
        trace_actual = go.Scatter(
            x=self.record['t'],
            y=self.record['taufric' + str(joint_number)],
            mode='lines',
            name='tauFric'
        )
        layout = go.Layout(
            title=f'Joint {joint_number} Friction Torque',
            xaxis=dict(
                title='Time (m)',
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            yaxis=dict(
                title='Joint Friction torque (Nm)',
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            margin=dict(l=40, r=40, t=40, b=40),
            width=width,
            height=height,
            plot_bgcolor='white',  # White background
            paper_bgcolor='white'
        )
        fig = go.Figure(data=[trace_actual], layout=layout)
        if(plotShow):
            iplot(fig)
        # iplot(fig)    

        # Generate file name based on joint number
        file_name = f'Joint_{joint_number}_Friction_Torque.png'    
        # Save the plot as a PNG file at the specified base path
        full_path = os.path.join(base_path, file_name)
        fig.write_image(full_path) 

    def plot_joint_tor(self, joint_number, width=800, height=600):
        trace_actual = go.Scatter(
            x=self.record['t'],
            y=self.record['tauact' + str(joint_number)],
            mode='lines',
            name='tauAct'
        )
        trace_desired = go.Scatter(
            x=self.record['t'],
            y=self.record['tau' + str(joint_number)],
            mode='lines+markers',
            name='tau',
            line=dict(dash='dash')
        )
        trace_idyn = go.Scatter(
            x=self.record['t'],
            y=self.record['tauidyn' + str(joint_number)],
            mode='lines+markers',
            name='tauIdyn',
            line=dict(dash='dash')
        )
        trace_ref = go.Scatter(
            x=self.record['t'],
            y=self.record['tauref' + str(joint_number)],
            mode='lines+markers',
            name='tauRef',
            line=dict(dash='dash')
        )
        trace_grav = go.Scatter(
            x=self.record['t'],
            y=self.record['taugrav' + str(joint_number)],
            mode='lines+markers',
            name='tauGrav',
            line=dict(dash='dash')
        )
        trace_fric = go.Scatter(
            x=self.record['t'],
            y=self.record['taufric' + str(joint_number)],
            mode='lines+markers',
            name='tauFric',
            line=dict(dash='dash')
        )
        trace_ext = go.Scatter(
            x=self.record['t'],
            y=self.record['tauext' + str(joint_number)],
            mode='lines+markers',
            name='tauExt',
            line=dict(dash='dash')
        )

         # Define a list of all traces
        traces = [trace_actual, trace_desired, trace_idyn, trace_ref, trace_grav, trace_fric, trace_ext]

        layout = go.Layout(
            title=f'Joint {joint_number} Torque Plot',
            # ... other layout settings ...
            updatemenus=[{
                'buttons': [
                    {
                        'args': ['visible', [True if i == j else False for j in range(len(traces))]],
                        'label': f'Show only {trace["name"]}',
                        'method': 'restyle'
                    }
                    for i, trace in enumerate(traces)
                ] + [
                    {
                        'args': ['visible', [True] * len(traces)],
                        'label': 'Show All',
                        'method': 'restyle'
                    },
                    {
                        'args': ['visible', [False] * len(traces)],
                        'label': 'Hide All',
                        'method': 'restyle'
                    }
                ],
                'direction': 'down',
                'showactive': True,
                'x': 0.1,
                'xanchor': 'left',
                'y': 1.1,
                'yanchor': 'top'
            }],
            xaxis=dict(
                title='Time (s)',
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            yaxis=dict(
                title='Joint torque (Nm)',
                gridcolor='#D3D3D3',
                gridwidth=1,
                griddash='dash',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=True
                ),
            margin=dict(l=40, r=40, t=40, b=40),
            width=width,
            height=height,
            plot_bgcolor='white',  # White background
            paper_bgcolor='white'
        )
        
        fig = go.Figure(data=[trace_actual, trace_desired, trace_idyn, trace_ref, trace_grav, trace_fric, trace_ext], layout=layout)
        iplot(fig) 

    def plot_path_actual_vs_desired(self, joint_number, base_path, width=600, height=400):
        # Mapping for joint numbers to labels
        labels = {1: 'X', 2: 'Y', 3: 'Z', 4: 'U', 5: 'V', 6: 'W'}

        # Determine label based on joint_number
        if joint_number not in labels:
            raise ValueError("Invalid joint number")
        
        label = labels[joint_number]
        path_type = 'Translation' if joint_number <= 3 else 'Rotation'

        # Actual and desired path data
        actual_path = np.array(self.record['p' + str(joint_number)])
        desired_path = np.array(self.record['pd' + str(joint_number)])

        trace_actual = go.Scatter(
            x=self.record['t'],
            y=actual_path,
            mode='lines',
            name=f'Actual {label} {path_type}',
            line=dict(width=2, color='blue')
        )

        trace_desired = go.Scatter(
            x=self.record['t'],
            y=desired_path,
            mode='lines',
            name=f'Desired {label} {path_type}',
            line=dict(width=2, color='green', dash='dash')
        )

        layout = go.Layout(
            title=f'{label} {path_type} Path: Actual vs Desired',
            xaxis=dict(title='Time (s)', gridcolor='#D3D3D3', griddash='dash', showline=True, linewidth=1, linecolor='#D3D3D3', mirror=True),
            yaxis=dict(title=f'{label} {path_type} Value', gridcolor='#D3D3D3', griddash='dash', showline=True, linewidth=1, linecolor='#D3D3D3', mirror=True),
            margin=dict(l=40, r=40, t=40, b=40),
            width=width,
            height=height,
            plot_bgcolor='white',
            paper_bgcolor='white'
        )

        fig = go.Figure(data=[trace_actual, trace_desired], layout=layout)
        
        # Generate file name and save the plot
        file_name = f'{label}_{path_type}_Path_Actual_vs_Desired.png'
        full_path = os.path.join(base_path, file_name)
        fig.write_image(full_path)


    def plot_error_task_translation_rotation(self, joint_number,base_path, width=600, height=400):
        # Mapping for joint numbers to labels
        labels = {1: 'X', 2: 'Y', 3: 'Z', 4: 'U', 5: 'V', 6: 'W'}

        # Determine error type and label based on joint_number
        if joint_number in [1, 2, 3]:
            error_type = 'translation'
        elif joint_number in [4, 5, 6]:
            error_type = 'rotation'
        else:
            raise ValueError("Invalid joint number")
        
        label = labels[joint_number]

        errors = np.array(self.record['pe' + str(joint_number)])
        rms_error = np.sqrt(np.mean(errors**2))
        max_error = np.max(np.abs(errors))

        trace_error = go.Scatter(
            x=self.record['t'],
            y=errors,
            mode='lines',
            name=f'{label} {error_type.capitalize()} Error',
            line=dict(width=4)  # Line thickness
        )

        # Using <span> with background color and text color (highlight) for values
        annotation_text = (
            f'RMS Error: <span style="color:red; font-weight:bold; background-color:yellow;">{rms_error:.6f}</span> rad/s, '
            f'Max Error: <span style="color:red; font-weight:bold; background-color:yellow;">{max_error:.6f}</span> rad/s'
        )

        annotations = [
            dict(
                xref='paper', yref='paper',
                x=0.5, y=1.05,
                xanchor='center', yanchor='top',
                # text=f'RMS Error: {rms_error:.6f} rad, Max Error: {max_error:.6f} rad',
                text=annotation_text,
                font=dict(family='Arial', size=16, color='red'),
                showarrow=False,
                bgcolor='white',         # White background for the annotation
                bordercolor='#D3D3D3',     # Border color for the annotation
                borderwidth=2            # Border width for the annotation
            )
        ]

        # Modify title and filename based on error_type and label
        title = f'{label} {error_type.capitalize()} Error'
        file_name = f'{label}_{error_type.capitalize()}_Error.png'

        layout = go.Layout(
            title=title,
            xaxis=dict(
                title='Time (s)',
                gridcolor='#D3D3D3',  # Light gray grid lines for x-axis
                gridwidth=1,
                griddash='dash',  # Dashed grid lines
                showline=True,      # These lines
                linewidth=1,       # and these settings add the box
                linecolor='#D3D3D3', # around the plot
                mirror=True        # Reflects the axis line on the opposite side
            ),
            yaxis=dict(
                title='Error (rad/s)',
                gridcolor='#D3D3D3',  # Light gray grid lines for y-axis
                gridwidth=1,
                griddash='dash',
                showline=True,      # These lines
                linewidth=1,       # and these settings add the box
                linecolor='#D3D3D3', # around the plot
                mirror=True        # Reflects the axis line on the opposite side
            ),
            annotations=annotations,
            margin=dict(l=40, r=40, t=40, b=40),
            width=width,
            height=height,
            plot_bgcolor='white',  # White background
            paper_bgcolor='white'
        )

        fig = go.Figure(data=[trace_error], layout=layout)
        # iplot(fig)

        # Generate file name based on joint number
        # file_name = f'Joint_{joint_number}_Tracking_Error.png'    
        # Save the plot as a PNG file at the specified base path
        full_path = os.path.join(base_path, file_name)
        fig.write_image(full_path) 

        return rms_error, max_error
    
    def extract_errors_translation_rotation(self, base_path, num_joints=6):
        translation_labels = {1: 'X', 2: 'Y', 3: 'Z'}
        rotation_labels = {4: 'U', 5: 'V', 6: 'W'}
        translation_errors = []
        rotation_errors = []

        for joint_number in range(1, num_joints + 1):
            rms_error, max_error = self.plot_error_task_translation_rotation(joint_number, base_path)

            if joint_number <= 3:  # Translation (X, Y, Z)
                label = translation_labels[joint_number]
                translation_errors.append([label, rms_error, max_error])
            else:  # Rotation (U, V, W)
                label = rotation_labels[joint_number]
                rotation_errors.append([label, rms_error, max_error])

        return translation_errors, rotation_errors
    
    def plot_path_velocity_actual_vs_desired(self, joint_number, base_path, width=600, height=400):
        # Mapping for joint numbers to labels
        labels = {1: 'X', 2: 'Y', 3: 'Z', 4: 'U', 5: 'V', 6: 'W'}

        # Determine label based on joint_number
        if joint_number not in labels:
            raise ValueError("Invalid joint number")
        
        label = labels[joint_number]
        path_type = 'Translation' if joint_number <= 3 else 'Rotation'

        # Actual and desired path data
        actual_path = np.array(self.record['pdot' + str(joint_number)])
        desired_path = np.array(self.record['pdotd' + str(joint_number)])

        trace_actual = go.Scatter(
            x=self.record['t'],
            y=actual_path,
            mode='lines',
            name=f'Actual {label} {path_type}',
            line=dict(width=2, color='blue')
        )

        trace_desired = go.Scatter(
            x=self.record['t'],
            y=desired_path,
            mode='lines',
            name=f'Desired {label} {path_type}',
            line=dict(width=2, color='green', dash='dash')
        )

        layout = go.Layout(
            title=f'{label} {path_type} Path Velocity: Actual vs Desired',
            xaxis=dict(title='Time (s)', gridcolor='#D3D3D3', griddash='dash', showline=True, linewidth=1, linecolor='#D3D3D3', mirror=True),
            yaxis=dict(title=f'{label} {path_type} Value', gridcolor='#D3D3D3', griddash='dash', showline=True, linewidth=1, linecolor='#D3D3D3', mirror=True),
            margin=dict(l=40, r=40, t=40, b=40),
            width=width,
            height=height,
            plot_bgcolor='white',
            paper_bgcolor='white'
        )

        fig = go.Figure(data=[trace_actual, trace_desired], layout=layout)
        
        # Generate file name and save the plot
        file_name = f'{label}_{path_type}_Path_Velocity_Actual_vs_Desired.png'
        full_path = os.path.join(base_path, file_name)
        fig.write_image(full_path)

    def plot_error_task_velocity(self, joint_number,base_path, width=600, height=400):
        # Mapping for joint numbers to labels
        labels = {1: 'X', 2: 'Y', 3: 'Z', 4: 'U', 5: 'V', 6: 'W'}

        # Determine error type and label based on joint_number
        if joint_number in [1, 2, 3]:
            error_type = 'translation'
        elif joint_number in [4, 5, 6]:
            error_type = 'rotation'
        else:
            raise ValueError("Invalid joint number")
        
        label = labels[joint_number]

        errors = np.array(self.record['pdote' + str(joint_number)])
        rms_error = np.sqrt(np.mean(errors**2))
        max_error = np.max(np.abs(errors))

        trace_error = go.Scatter(
            x=self.record['t'],
            y=errors,
            mode='lines',
            name=f'{label} {error_type.capitalize()} Error',
            line=dict(width=4)  # Line thickness
        )

        # Using <span> with background color and text color (highlight) for values
        annotation_text = (
            f'RMS Error: <span style="color:red; font-weight:bold; background-color:yellow;">{rms_error:.6f}</span> rad/s, '
            f'Max Error: <span style="color:red; font-weight:bold; background-color:yellow;">{max_error:.6f}</span> rad/s'
        )

        annotations = [
            dict(
                xref='paper', yref='paper',
                x=0.5, y=1.05,
                xanchor='center', yanchor='top',
                # text=f'RMS Error: {rms_error:.6f} rad, Max Error: {max_error:.6f} rad',
                text=annotation_text,
                font=dict(family='Arial', size=16, color='red'),
                showarrow=False,
                bgcolor='white',         # White background for the annotation
                bordercolor='#D3D3D3',     # Border color for the annotation
                borderwidth=2            # Border width for the annotation
            )
        ]

        # Modify title and filename based on error_type and label
        title = f'{label} {error_type.capitalize()} Error'
        file_name = f'{label}_{error_type.capitalize()}_Error.png'

        layout = go.Layout(
            title=title,
            xaxis=dict(
                title='Time (s)',
                gridcolor='#D3D3D3',  # Light gray grid lines for x-axis
                gridwidth=1,
                griddash='dash',  # Dashed grid lines
                showline=True,      # These lines
                linewidth=1,       # and these settings add the box
                linecolor='#D3D3D3', # around the plot
                mirror=True        # Reflects the axis line on the opposite side
            ),
            yaxis=dict(
                title='Error (rad/s)',
                gridcolor='#D3D3D3',  # Light gray grid lines for y-axis
                gridwidth=1,
                griddash='dash',
                showline=True,      # These lines
                linewidth=1,       # and these settings add the box
                linecolor='#D3D3D3', # around the plot
                mirror=True        # Reflects the axis line on the opposite side
            ),
            annotations=annotations,
            margin=dict(l=40, r=40, t=40, b=40),
            width=width,
            height=height,
            plot_bgcolor='white',  # White background
            paper_bgcolor='white'
        )

        fig = go.Figure(data=[trace_error], layout=layout)
        # iplot(fig)

        # Generate file name based on joint number
        # file_name = f'Joint_{joint_number}_Tracking_Error.png'    
        # Save the plot as a PNG file at the specified base path
        full_path = os.path.join(base_path, file_name)
        fig.write_image(full_path) 

        return rms_error, max_error
    
    def extract_errors_task_velocity(self, base_path, num_joints=6):
        errors = {}
        for joint_number in range(1, num_joints + 1):
            rms_error, max_error = self.plot_error_task_velocity(joint_number, base_path)
            errors[joint_number] = {'RMS Error': rms_error, 'Max Error': max_error}
        return errors
    
    def generate_pdf_report_task_with_gains(self, translation_errors, rotation_errors, gains, pdf_path):
        styles = getSampleStyleSheet()

        # Create tables for translation and rotation errors
        elements = []

        # Translation Errors Table
        translation_data = [['Axis', 'RMS Error (mm)', 'Max Error (mm)']] + translation_errors
        translation_table = Table(translation_data)
        translation_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(Paragraph('Translation Errors', styles['Heading2']))
        elements.append(Spacer(1, 12))
        elements.append(translation_table)
        elements.append(Spacer(1, 24))

        # Rotation Errors Table
        rotation_data = [['Axis', 'RMS Error (°)', 'Max Error (°)']] + rotation_errors
        rotation_table = Table(rotation_data)
        rotation_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(Paragraph('Rotation Errors', styles['Heading2']))
        elements.append(Spacer(1, 12))
        elements.append(rotation_table)

        # Task Control Gain Table
        # Reformatted Task Control Gain Table
        # Extract gains for each axis and create table rows
        gain_rows = []
        for i in range(len(gains['kp'])):  # Assuming each list in gains dict is of same length
            # gain_row = [f'Axis {i+1}', gains['kp'][i], gains['kv'][i], gains['kl2'][i]]
            gain_row = ['Axis ' + str(i+1), str(gains['kp'][i]), str(gains['kv'][i]), str(gains['kl2'][i])]
            gain_rows.append(gain_row)

        gains_data = [['Axis', 'Kp', 'Kv', 'KL2']] + gain_row
        gains_table = Table(gains_data)
        gains_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(Paragraph('Task Control Gains', styles['Heading2']))
        elements.append(Spacer(1, 12))
        elements.append(gains_table)

        # Create a PDF document
        pdf = SimpleDocTemplate(pdf_path, pagesize=letter)
        pdf.build(elements)

    def generate_pdf_report_task_control_mod(self, translation_errors, rotation_errors, joint_gain, pdf_path):
        # Create DataFrames
        # df_pos = pd.DataFrame(translation_errors).T
        # df_vel = pd.DataFrame(rotation_errors).T
         # Create a general title for the page
        styles = getSampleStyleSheet()
        page_title = Paragraph("Control Performance Report", styles['Title'])
        formatted_translation_errors = [[axis, f'{rms:.3e}', f'{max_err:.3e}'] for axis, rms, max_err in translation_errors]
        formatted_rotation_errors = [[axis, f'{rms:.3e}', f'{max_err:.3e}'] for axis, rms, max_err in rotation_errors]
        # df_translation = pd.DataFrame(formatted_translation_errors).T
        # df_rotation = pd.DataFrame(formatted_rotation_errors).T
        df_gains = pd.DataFrame(joint_gain)

        # df_translation['RMS Error'] = df_translation['RMS Error'].apply(lambda x: f'{x:.3e}')
        # df_rotation['Max Error'] = df_rotation['Max Error'].apply(lambda x: f'{x:.3e}')
        # Create DataFrames
        df_translation = pd.DataFrame(formatted_translation_errors, columns=['Axis', 'RMS Error (mm)', 'Max Error (mm)'])
        df_rotation = pd.DataFrame(formatted_rotation_errors, columns=['Axis', 'RMS Error (°)', 'Max Error (°)'])
        
        # df_translation.index.name = 'Axis'
        # df_translation.reset_index(inplace=True)
        # df_translation
        # df_translation.columns = ['Axis', 'RMS Error (mm)', 'Max Error (mm)']

        # df_rotation.index.name = 'Axis'
        # df_rotation.reset_index(inplace=True)
        # df_rotation.columns = ['Axis', 'RMS Error (°)', 'Max Error (°)']

        df_gains.index.name = 'Joint Number'
        df_gains.reset_index(inplace=True)
        df_gains['Joint Number'] = df_gains['Joint Number'] + 1
        df_gains['Joint Number'] = df_gains['Joint Number'].astype(int)  
        df_gains.columns = ['Joint Number', 'Kp', 'Kv', 'KL2'] 


         # Create tables with titles
        elements = [page_title, Spacer(1, 15)]
        elements += self.create_table(df_translation, "Task Space Motion: Translation Errors") + [Spacer(1, 24)]
        elements += self.create_table(df_rotation, "Task Space Motion: Rotation Errors") + [Spacer(1, 24)]
        elements += self.create_table(df_gains, "Task Control Gains")

        # Create a PDF document
        pdf = SimpleDocTemplate(pdf_path, pagesize=letter)
        pdf.build(elements)


    def generate_pdf_report_task_control_mod(self, translation_errors, rotation_errors, joint_gain, payload,  test_velocity, test_acceleration, pdf_path):
        # Introductory information
        styles = getSampleStyleSheet()
        title = Paragraph("Robot Control Performance Report", styles['Title'])
        payload_info = Paragraph(f"<b>Payload:</b> {payload} kg", styles['BodyText'])
        velocity_info = Paragraph(f"<b>Velocity level:</b> {test_velocity} %", styles['BodyText'])
        acceleration_info = Paragraph(f"<b>Acceleration level:</b> {test_acceleration} %", styles['BodyText'])
        # Create DataFrames
        # df_pos = pd.DataFrame(translation_errors).T
        # df_vel = pd.DataFrame(rotation_errors).T
         # Create a general title for the page
        # Convert translation errors from meters to millimeters
        formatted_translation_errors = [
            [axis, rms * 1000, max_err * 1000] for axis, rms, max_err in translation_errors
        ]

        # page_title = Paragraph("Control Performance Report", styles['Title'])
        formatted_translation_errors = [[axis, f'{rms:.3e}', f'{max_err:.3e}'] for axis, rms, max_err in formatted_translation_errors]
        formatted_rotation_errors = [[axis, f'{rms:.3e}', f'{max_err:.3e}'] for axis, rms, max_err in rotation_errors]
        # df_translation = pd.DataFrame(formatted_translation_errors).T
        # df_rotation = pd.DataFrame(formatted_rotation_errors).T
        df_gains = pd.DataFrame(joint_gain)

        # df_translation['RMS Error'] = df_translation['RMS Error'].apply(lambda x: f'{x:.3e}')
        # df_rotation['Max Error'] = df_rotation['Max Error'].apply(lambda x: f'{x:.3e}')
        # Create DataFrames
        df_translation = pd.DataFrame(formatted_translation_errors, columns=['Axis', 'RMS Error (mm)', 'Max Error (mm)'])
        df_rotation = pd.DataFrame(formatted_rotation_errors, columns=['Axis', 'RMS Error (°)', 'Max Error (°)'])
        
        # df_translation.index.name = 'Axis'
        # df_translation.reset_index(inplace=True)
        # df_translation
        # df_translation.columns = ['Axis', 'RMS Error (mm)', 'Max Error (mm)']

        # df_rotation.index.name = 'Axis'
        # df_rotation.reset_index(inplace=True)
        # df_rotation.columns = ['Axis', 'RMS Error (°)', 'Max Error (°)']

        df_gains.index.name = 'Joint Number'
        df_gains.reset_index(inplace=True)
        df_gains['Joint Number'] = df_gains['Joint Number'] + 1
        df_gains['Joint Number'] = df_gains['Joint Number'].astype(int)  
        df_gains.columns = ['Joint Number', 'Kp', 'Kv', 'KL2'] 


         # Create tables with titles
        # elements = [page_title, Spacer(1, 15)]
        elements = [title, Spacer(1, 12), payload_info, Spacer(1, 12), velocity_info, Spacer(1, 12), acceleration_info, Spacer(1, 24)]
        elements += self.create_table(df_translation, "Task Space Motion: Translation Errors") + [Spacer(1, 24)]
        elements += self.create_table(df_rotation, "Task Space Motion: Rotation Errors") + [Spacer(1, 24)]
        elements += self.create_table(df_gains, "Task Control Gains")

        # Create a PDF document
        pdf = SimpleDocTemplate(pdf_path, pagesize=letter)
        pdf.build(elements)

    
    def generate_pdf_report_full(self, translation_errors, rotation_errors, pdf_path):
        styles = getSampleStyleSheet()

        # Create tables for translation and rotation errors
        elements = []

        # Translation Errors Table
        translation_data = [['Axis', 'RMS Error (mm)', 'Max Error (mm)']] + translation_errors
        translation_table = Table(translation_data)
        translation_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(Paragraph('Translation Errors', styles['Heading2']))
        elements.append(Spacer(1, 12))
        elements.append(translation_table)
        elements.append(Spacer(1, 24))

        # Rotation Errors Table
        rotation_data = [['Axis', 'RMS Error (°)', 'Max Error (°)']] + rotation_errors
        rotation_table = Table(rotation_data)
        rotation_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(Paragraph('Rotation Errors', styles['Heading2']))
        elements.append(Spacer(1, 12))
        elements.append(rotation_table)

        # Create a PDF document
        pdf = SimpleDocTemplate(pdf_path, pagesize=letter)
        pdf.build(elements)

    def generate_pdf_report_old(self, position_errors, velocity_errors, pdf_path):
        # Create DataFrames
        df_pos = pd.DataFrame(position_errors).T

        # Format the DataFrames
        for df in [df_pos]:
            df.index.name = 'Joint Number'
            df.reset_index(inplace=True)
            df['Joint Number'] = df['Joint Number'].astype(int)
            df['RMS Error'] = df['RMS Error'].apply(lambda x: f'{x:.3e}')
            df['Max Error'] = df['Max Error'].apply(lambda x: f'{x:.3e}')
            df.columns = ['Joint Number', 'RMS Error', 'Max Error']

        # Create tables with titles
        df_pos.columns = ['Joint Number', 'RMS Error (mm)', 'Max Error (deg)']    
        elements = self, create_table(df_pos, "TCP Tracking Errors") + [Spacer(1, 24)] 
        # Create a PDF document
        pdf = SimpleDocTemplate(pdf_path, pagesize=letter)
        
        # Build the PDF
        pdf.build(elements)

    def create_table_oldold(self, df, title):
        # Title for the table
        styles = getSampleStyleSheet()
        title = Paragraph(title, styles['Heading2'])

        # Convert DataFrame to a list of lists for ReportLab Table
        data = [df.columns.to_list()] + df.values.tolist()
        table = Table(data)

        # Add style to the table
        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ])
        table.setStyle(style)

        return [title, Spacer(1, 12), table]
    
    def create_table(self, df, title_text):
        styles = getSampleStyleSheet()
        title = Paragraph(title_text, styles['Heading3'])
        title_style = ParagraphStyle(
            name='CenteredTitle',
            parent=styles['Heading3'],
            alignment=TA_CENTER
        )
        centered_title = Paragraph(title_text, title_style)

        # Convert DataFrame to a list of lists for ReportLab Table
        data = [df.columns.to_list()] + df.values.tolist()
        table = Table(data)

        # Add style to the table
        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ])
        table.setStyle(style)

        return [centered_title, Spacer(1, 12), table]

    
    def generate_comprehensive_pdf_report(self, position_errors, velocity_errors, translation_errors, rotation_errors, pdf_path):
        # Create a general title for the page
        styles = getSampleStyleSheet()
        page_title = Paragraph("Control Performance Report", styles['Title'])
        
        # Create DataFrames
            # Create DataFrames
        df_pos = pd.DataFrame(position_errors).T
        df_vel = pd.DataFrame(velocity_errors).T
            # Format the DataFrames
        for df in [df_pos, df_vel]:
            df.index.name = 'Joint Number'
            df.reset_index(inplace=True)
            df['Joint Number'] = df['Joint Number'].astype(int)
            df['RMS Error'] = df['RMS Error'].apply(lambda x: f'{x:.3e}')
            df['Max Error'] = df['Max Error'].apply(lambda x: f'{x:.3e}')
            df.columns = ['Joint Number', 'RMS Error', 'Max Error']

            # Create tables with titles
        df_pos.columns = ['Joint Number', 'RMS Error (rad)', 'Max Error (rad)']    
        df_vel.columns = ['Joint Number', 'RMS Error (rad/s)', 'Max Error (rad/s)']   

        # df_pos = pd.DataFrame(position_errors, columns=['Joint Number', 'RMS Error (rad)', 'Max Error (rad)'])
        # df_vel = pd.DataFrame(velocity_errors, columns=['Joint Number', 'RMS Error (rad/s)', 'Max Error (rad/s)'])
        df_translation = pd.DataFrame(translation_errors, columns=['Axis', 'RMS Error (mm)', 'Max Error (mm)'])
        df_rotation = pd.DataFrame(rotation_errors, columns=['Axis', 'RMS Error (°)', 'Max Error (°)'])

        # Create tables with titles
        elements = [page_title, Spacer(1, 15)]
        elements = self.create_table(df_pos, "Joint Space Motion: Position Tracking Errors")
        elements += self.create_table(df_vel, "Joint Space Motion: Velocity Tracking Errors")
        elements += self.create_table(df_translation, "Task Space Motion: Translation Errors")
        elements += self.create_table(df_rotation, "Task Space Motion: Rotation Errors")

        # Create a PDF document
        pdf = SimpleDocTemplate(pdf_path, pagesize=letter)
        pdf.build(elements)

    def plot_X_Y(self):
        plt.figure(figsize=(10, 5), dpi=80)
        plt.plot(self.record['p1'], self.record['p2'], 'r', label='Actual', linewidth="4")
        plt.plot(self.record['pd1'], self.record['pd2'], 'k--', label='Desired', linewidth="4")
        plt.xlabel('X-axis)')
        plt.ylabel('Y-axis')
        plt.title('Position tracking plot')
        plt.legend()
        plt.grid(True)
        plt.show()

    def plot_Y_Z(self):
        plt.figure(figsize=(10, 5), dpi=80)
        plt.plot(self.record['p2'], self.record['p3'], 'r', label='Actual', linewidth="4")
        plt.plot(self.record['pd2'], self.record['pd3'], 'k--', label='Desired', linewidth="4")
        plt.xlabel('Y-axis)')
        plt.ylabel('Z-axis')
        plt.title('Position tracking plot')
        plt.legend()
        plt.grid(True)
        plt.show()

    def plot_Z_X(self):
        plt.figure(figsize=(10, 5), dpi=80)
        plt.plot(self.record['p3'], self.record['p2'], 'r', label='Actual', linewidth="4")
        plt.plot(self.record['pd3'], self.record['pd2'], 'k--', label='Desired', linewidth="4")
        plt.xlabel('Z-axis)')
        plt.ylabel('X-axis')
        plt.title('Position tracking plot')
        plt.legend()
        plt.grid(True)
        plt.show()

    def plot_X_error(self):
        plt.figure(figsize=(10, 5), dpi=80)
        plt.plot(self.record['t'], self.record['pe1'], 'k', linewidth="4")
        plt.xlabel('Time (s)')
        plt.ylabel('Error (m)')
        plt.title('Position tracking plot')
        plt.legend()
        # plt.ylim([0, max( self.record['fe6'])+5])
        plt.grid(True)
        plt.show()    

    def plot_Y_error(self):
        plt.figure(figsize=(10, 5), dpi=80)
        plt.plot(self.record['t'], self.record['pe2'], 'k', linewidth="4")
        plt.xlabel('Time (s)')
        plt.ylabel('Error (m)')
        plt.title('Position tracking plot')
        plt.legend()
        # plt.ylim([0, max( self.record['fe6'])+5])
        plt.grid(True)
        plt.show()         

    def plot_Z_error(self):
        plt.figure(figsize=(10, 5), dpi=80)
        plt.plot(self.record['t'], self.record['pe3'], 'k', linewidth="4")
        plt.xlabel('Time (s)')
        plt.ylabel('Error (m)')
        plt.title('Position tracking plot')
        plt.legend()
        # plt.ylim([0, max( self.record['fe6'])+5])
        plt.grid(True)
        plt.show()                


class RobotPlotter:
    def __init__(self, record):
        if record is None:
            raise ValueError("Record data is None. Please provide valid data.")
        self.record = record

    def plot_robot_and_desired_paths(self):
        # Define the number of rows and columns for subplots
        rows, cols = 3, 2

        # Create a figure and a set of subplots
        fig, axs = plt.subplots(rows, cols, figsize=(12, 18), dpi=80)

        # Iterate through each joint and plot
        for i in range(1, 7):
            ax = axs[(i-1)//cols, (i-1)%cols]  # Determine the position of the subplot
            ax.plot(self.record['t'], self.record[f'q{i}'], 'b', label='Actual Path')
            ax.plot(self.record['t'], self.record[f'qd{i}'], 'r--', label='Desired Path')
            ax.set_xlabel('Time (m)')
            ax.set_ylabel('Joint Pose (rad)')
            ax.set_title(f'Joint {i} Pose Tracking')
            ax.legend()
            ax.grid(True)

        # Adjust the layout
        plt.tight_layout()
        plt.show()
    
