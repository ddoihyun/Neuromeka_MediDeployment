import sys
import os
import platform

import signal
import sys
import grpc
from time import sleep
from concurrent import futures
import json

import common as Common
import logging
import argparse
import os
import json
import shutil
import datetime
import zipfile
import subprocess
import urllib
from common.utils import load_json, write_json, get_abs_path

PYTHON_MIDDLEWARE_DIR = os.path.dirname(os.path.abspath(__file__))
DEPLOYMENT_DIR = os.path.abspath(os.path.join(PYTHON_MIDDLEWARE_DIR, os.pardir))
CONFIGURATION_DIR = os.path.normpath(os.path.join(DEPLOYMENT_DIR, '../IndyConfigurations'))
SAFETY_ADDRESS_DEFAULT = '192.168.7.2'
INSTALL_PATH = os.path.join(DEPLOYMENT_DIR, 'install')
UPDATE_FILE_DEFAULT = os.path.join(INSTALL_PATH, "IndyDeploymentBBB.zip")
ATTACHMENT_DIR = os.path.join(DEPLOYMENT_DIR, "Attachments")

def run_commandline(commandline):
    result = subprocess.run(commandline)
    return result.returncode

BBB_UPDATE_ERR_DICT = {
    1: "Fail to connect to SafetyBoard",
    2: "Failed to backup SafetyBoard",
    3: "Failed to download SafetyBoard Binary",
    4: "Failed to unzip SafetyBoard Binary",
    5: "Failed to send New Files to SafetyBoard",
    6: "Failed to Install SafetyBoard",
    7: "Failed to Reboot SafetyBoard"
}

def install_sshpass() -> bool:
    try:
        ret = run_commandline(["sshpass", "-V"])
        if ret == 0:
            return True
    except Exception as e:
        print(f"sshpass error {e} - try install sshpass")
    arch = platform.architecture()[0]
    install_file = None
    if arch == '64bit':
        install_file = "sshpass_1.09-1_amd64.deb"
    elif arch == '32bit':
        install_file = "sshpass_1.06-1_i386.deb"
    else:
        print(f"Architecture unimplemented to install sshpass: {arch}")
        return False
    install_file = os.path.join(ATTACHMENT_DIR, install_file)
    try:
        ret = run_commandline(["sudo", "dpkg", "-i", install_file])
        return ret == 0
    except Exception as e:
        print(f"install sshpass error: {e}")
    return False

def update_bbb(file, config=Common.Config.CONFIG_JSON_DEFAULT, address=SAFETY_ADDRESS_DEFAULT,
               update_binary=True):
    # 사용 여부 체크
    conig_path_dict = load_json(get_abs_path(config))
    config_dict = {}
    config_file = "/home/user/release/IndyDeployment/indyConfig.json"
    if (conig_path_dict is not None) and ('Config' in conig_path_dict):
        config_file = get_abs_path(conig_path_dict['Config'])
        config_dict = load_json(config_file)

    use_safetyio = False
    if "ControlBox" in config_dict:
        cb_config = config_dict["ControlBox"]
        if "use_safetyio" in cb_config:
            use_safetyio = cb_config["use_safetyio"]
        elif "type" in cb_config:
            use_safetyio = (cb_config["type"] == "CB3.0")

    if use_safetyio:
        safety_address = address

        # 테스트
        print("Test SafetyBoard Connection")
        if install_sshpass():
            ret = run_commandline([
                "sshpass", "-p", "root",
                "ssh", "-o", "ConnectTimeout=1", f"root@{safety_address}", "ls /home"
            ])
        else:
            print("Failed to install sshpass")
            ret = 1
        if ret != 0:
            print(BBB_UPDATE_ERR_DICT[1])
            return 1

        if update_binary:
            # 종료
            print("Kill SafetyBoard Processes")
            ret = run_commandline([
                "sshpass", "-p", "root",
                "ssh", f"root@{safety_address}", "/home/debian/release/IndyDeploymentBBB/killBBB.sh"
            ])
            if ret != 0:
                print("Fail to kill returned from SafetyBoard - can be bug from old ver. keep working")

            # 백업
            print("Backup SafetyBoard Files")
            ret = run_commandline([
                "sshpass", "-p", "root",
                "ssh", f"root@{safety_address}", "rm -rf /home/debian/release/IndyDeploymentBBB-backup"
            ])
            if ret != 0:
                print(BBB_UPDATE_ERR_DICT[2])
                return 2
            ret = run_commandline([
                "sshpass", "-p", "root",
                "ssh", f"root@{safety_address}", "cp -r /home/debian/release/IndyDeploymentBBB /home/debian/release/IndyDeploymentBBB-backup"
            ])
            if ret != 0:
                print(BBB_UPDATE_ERR_DICT[2])
                return 2

        ret = run_commandline([
            "sshpass", "-p", "root",
            "ssh", f"root@{safety_address}", "rm -rf /home/debian/release/IndyConfigurations-backup"
        ])
        if ret != 0:
            print(BBB_UPDATE_ERR_DICT[2])
            return 2
        ret = run_commandline([
            "sshpass", "-p", "root",
            "ssh", f"root@{safety_address}", "cp -r /home/debian/release/IndyConfigurations /home/debian/release/IndyConfigurations-backup"
        ])
        if ret != 0:
            print(BBB_UPDATE_ERR_DICT[2])
            return 2

        if update_binary:
            # 바이너리 업데이트
            print(f"Get SafetyBoard Binary File {file}")
            if ".com" in file:
                binary_filename = os.path.basename(urllib.parse.unquote(urllib.parse.urlparse(file).path))
                result = ret = run_commandline([
                    "wget", file, "-O", os.path.join(INSTALL_PATH, binary_filename)
                ])
                if ret != 0:
                    print(BBB_UPDATE_ERR_DICT[3])
                    return 3
                binary_file = os.path.join(INSTALL_PATH, binary_filename)
            else:
                binary_file = file
                binary_filename = os.path.basename(binary_file)
            binary_folder = os.path.join(INSTALL_PATH, "IndyDeploymentBBB")
            if os.path.isdir(binary_folder):
                shutil.rmtree(binary_folder)
            os.mkdir(binary_folder)

            print("Unzip SafetyBoard Binary")
            ret = run_commandline([
                f"unzip", "-o", binary_file, "-d", binary_folder
            ])
            os.remove(binary_file)
            if ret != 0:
                print(BBB_UPDATE_ERR_DICT[4])
                print(f"File: {binary_file}")
                return 4

            print("Update SafetyBoard Binary")
            ret = run_commandline([
                "sshpass", "-p", "root",
                "scp", "-r", binary_folder, f"root@{safety_address}:/home/debian/release/"
            ])
            if ret != 0:
                print(BBB_UPDATE_ERR_DICT[5])
                return 5

        # 컨피그 업데이트
        print("Update SafetyBoard Configs")
        ret = run_commandline([
            "sshpass", "-p", "root",
            "scp", "-r", CONFIGURATION_DIR, f"root@{safety_address}:/home/debian/release/"
        ])
        if ret != 0:
            print(BBB_UPDATE_ERR_DICT[5])
            return 5

        ret = run_commandline([
            "sshpass", "-p", "root",
            "scp", "-r", config_file, f"root@{safety_address}:/home/debian/release/IndyDeploymentBBB/"
        ])
        if ret != 0:
            print(BBB_UPDATE_ERR_DICT[5])
            return 5

        if update_binary:
            # BBB 인스톨
            print("Install SafetyBoard")
            ret = run_commandline([
                "sshpass", "-p", "root",
                "ssh", f"root@{safety_address}", f"bash /home/debian/release/IndyDeploymentBBB/install.sh"
            ])
            if ret != 0:
                print(BBB_UPDATE_ERR_DICT[6])
                return 6

            # 리부트
            print("Reboot SafetyBoard")
            ret = run_commandline([
                "sshpass", "-p", "root",
                "ssh", f"root@{safety_address}", f"reboot"
            ])
            if ret != 0:
                print(BBB_UPDATE_ERR_DICT[7])
                return 7
    return 0


def rollback_bbb(config=Common.Config.CONFIG_JSON_DEFAULT, address=SAFETY_ADDRESS_DEFAULT):
    # 사용 여부 체크
    conig_path_dict = load_json(get_abs_path(config))
    config_dict = {}
    config_file = "/home/user/release/IndyDeployment/indyConfig.json"
    if (conig_path_dict is not None) and ('Config' in conig_path_dict):
        config_file = get_abs_path(conig_path_dict['Config'])
        config_dict = load_json(config_file)

    use_safetyio = False
    if "ControlBox" in config_dict:
        cb_config = config_dict["ControlBox"]
        if "use_safetyio" in cb_config:
            use_safetyio = cb_config["use_safetyio"]
        elif "type" in cb_config:
            use_safetyio = (cb_config["type"] == "CB3.0")

    if use_safetyio:
        safety_address = address

        # 종료
        print("Kill SafetyBoard Processes")
        ret = run_commandline([
            "sshpass", "-p", "root",
            "ssh", f"root@{safety_address}", "/home/debian/release/IndyDeploymentBBB/killBBB.sh"
        ])
        if ret != 0:
            print("Fail to kill returned from SafetyBoard - can be bug from old ver. keep working")

        # 백업
        print("Backup SafetyBoard Files")
        ret = run_commandline([
            "sshpass", "-p", "root",
            "ssh", f"root@{safety_address}", "rm -rf /home/debian/release/IndyDeploymentBBB-rollback"
        ])
        if ret != 0:
            print("Failed to backup SafetyBoard")
            return 2
        ret = run_commandline([
            "sshpass", "-p", "root",
            "ssh", f"root@{safety_address}", "mv /home/debian/release/IndyDeploymentBBB /home/debian/release/IndyDeploymentBBB-rollback"
        ])
        if ret != 0:
            print("Failed to backup SafetyBoard")
            return 2
        ret = run_commandline([
            "sshpass", "-p", "root",
            "ssh", f"root@{safety_address}", "rm -rf /home/debian/release/IndyConfigurations-rollback"
        ])
        if ret != 0:
            print("Failed to backup SafetyBoard")
            return 2
        ret = run_commandline([
            "sshpass", "-p", "root",
            "ssh", f"root@{safety_address}", "cp -r /home/debian/release/IndyConfigurations /home/debian/release/IndyConfigurations-rollback"
        ])
        if ret != 0:
            print("Failed to backup SafetyBoard")
            return 2

        # 복원
        print("Rollback SafetyBoard Binary")
        ret = run_commandline([
            "sshpass", "-p", "root",
            "ssh", f"root@{safety_address}", "mv /home/debian/release/IndyDeploymentBBB-backup /home/debian/release/IndyDeploymentBBB"
        ])
        if ret != 0:
            print("Failed to rollback SafetyBoard")
            return 3
        ret = run_commandline([
            "sshpass", "-p", "root",
            "ssh", f"root@{safety_address}", "cp -r /home/debian/release/IndyConfigurations-backup /home/debian/release/IndyConfigurations"
        ])
        if ret != 0:
            print("Failed to rollback SafetyBoard")
            return 3

        # BBB 인스톨
        print("Install SafetyBoard")
        ret = run_commandline([
            "sshpass", "-p", "root",
            "ssh", f"root@{safety_address}", f"bash /home/debian/release/IndyDeploymentBBB/install.sh"
        ])
        if ret != 0:
            print("Failed to Install SafetyBoard")
            return 6

        # 리부트
        print("Reboot SafetyBoard")
        ret = run_commandline([
            "sshpass", "-p", "root",
            "ssh", f"root@{safety_address}", f"reboot"
        ])
        if ret != 0:
            print("Failed to Reboot SafetyBoard")
            return 7
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Indy Middleware')
    parser.add_argument('-f', '--file', required=False, type=str,
                        default=UPDATE_FILE_DEFAULT,help=f"Binary File for SafetyBoard")
    parser.add_argument('-c', '--config', required=False, type=str,
                        default=Common.Config.CONFIG_JSON_DEFAULT,
                        help=f"Configuration File (default: {Common.Config.CONFIG_JSON_DEFAULT})")
    parser.add_argument('-a', '--address', required=False, type=str,
                        default=SAFETY_ADDRESS_DEFAULT, help=f"IP address of SafetyBoard (default: {SAFETY_ADDRESS_DEFAULT})")
    parser.add_argument('-r', '--rollback', required=False, action='store_true',
                        default=False, help=f"roll back update")
    parser.add_argument('-d', '--debug', required=False, action='store_true',
                        default=False, help=f"set log level to DEBUG")
    args = parser.parse_args()
    ret = 0
    if args.rollback:
        print(f"Roll back BBB update")
        ret = rollback_bbb(args.config, args.address)
    else:
        print(f"Ubdate BBB with {args.file}")
        ret = update_bbb(args.file, args.config, args.address)
    exit(ret)
