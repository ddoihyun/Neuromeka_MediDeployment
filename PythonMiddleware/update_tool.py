import sys
import os

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
LOG_EXCLUDE_DIR = os.path.join(DEPLOYMENT_DIR, 'LogData/*/*')
RELEASE_PATH = os.path.abspath(os.path.join(DEPLOYMENT_DIR, os.pardir))
BACKUP_FILEPATH = os.path.join(RELEASE_PATH, "IndyFramework3Backup.zip")
DOWNLOAD_DIR = "/home/user/Downloads"
INSTALL_PATH = os.path.join(DEPLOYMENT_DIR, 'install')
UPDATE_FILE_DEFAULT = os.path.join(INSTALL_PATH, "IndyDeploymentBBB.zip")
VERSION_INFO_URL = "https://s3.ap-northeast-2.amazonaws.com/update.neuromeka.com/IndyFramework3/versions.json"

def run_commandline(commandline):
    result = subprocess.run(commandline)
    return result.returncode


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Indy Middleware')
    parser.add_argument('-p', '--platform', required=False, type=str,
                        default="STEP2",help=f"Version to install")
    parser.add_argument('-v', '--version', required=False, type=str,
                        default="",help=f"Version to install")
    parser.add_argument('-d', '--dependency', required=False, action='store_true',
                        default=False, help=f"set this flag to install requirements (default: False)")
    parser.add_argument('-s', '--safety', required=False, action='store_true',
                        default=False, help=f"set this flag to install safety update (default: False)")
    parser.add_argument('-r', '--rollback', required=False, action='store_true',
                        default=False, help=f"roll back update")
    args = parser.parse_args()
    ret = 0

    if args.rollback:
        print("Kill Framework")
        ret = run_commandline([os.path.join(DEPLOYMENT_DIR, "killTasks.sh")])
        if ret != 0:
            print("Failed to kill framework", ret)
            exit(1)

        print("Backup New Framework")
        run_commandline(["rm", "-rf", "/home/user/release/IndyDeployment-rollback"])
        run_commandline(["rm", "-rf", "/home/user/release/IndyConfigurations-rollback"])
        ret = run_commandline(["mv", "/home/user/release/IndyDeployment", "/home/user/release/IndyDeployment-rollback"])
        ret = ret and run_commandline(["mv", "/home/user/release/IndyConfigurations", "/home/user/release/IndyConfigurations-rollback"])

        if ret != 0:
            print("Failed to backup framework")
            exit(2)

        print("Unzip Backup")
        ret = run_commandline(["unzip", "-o", "/home/user/release/IndyFramework3Backup.zip", "-d", "/"])
        if ret != 0:
            print(f"Failed to unzip backup file {ret}")
            exit(3)

        print("Re-Install")
        ret = run_commandline(["bash", "/home/user/release/IndyDeployment/install/install.sh"])
        if ret != 0:
            print("Failed to re-install framework")
            exit(4)

        print("Rollback SafetyBoard")
        ret = run_commandline(["python3", "/home/user/release/IndyDeployment/PythonMiddleware/bbb_updater.py", "-r"])
        if ret != 0:
            print("Failed to rollback SafetyBoard")
            exit(5)

        print("Rollback DONE")

        print("Reboot")
        ret = run_commandline(["reboot"])
        if ret != 0:
            print("Failed to reboot")
            exit(6)
    else:
        print("Backup Framework")
        if os.path.isfile(BACKUP_FILEPATH):
            os.remove(BACKUP_FILEPATH)
        ret = run_commandline(["zip", "-ro", BACKUP_FILEPATH, DEPLOYMENT_DIR, CONFIGURATION_DIR, "-x", LOG_EXCLUDE_DIR])
        if ret != 0:
            print("Failed to backup framework")
            exit(2)

        if (args.dependency or args.safety):
            meta_filename = os.path.basename(urllib.parse.unquote(VERSION_INFO_URL))
            ret = run_commandline(["wget", VERSION_INFO_URL, "-O", os.path.join(DOWNLOAD_DIR, meta_filename)])
            if ret != 0:
                print("Failed to get online version data")
                exit(3)

            versions = load_json(os.path.join(DOWNLOAD_DIR, "versions.json"))
            versions_platform = versions[args.platform]
            if args.version == "":
                target_ver = versions_platform["latest"]["final"]
            else:
                target_ver = args.version

            print(f"Target Version: {target_ver}")
            ver_info = versions_platform[target_ver]

            app_link = ver_info["conty"]
            print(f"App link to install: {app_link} - skipped in this backend sequence test")
            print(f"\t Download, install app, send framework file and request UpdateIndySW")

            print(f"Target Version: {target_ver}")

            if args.dependency:
                requirements = ver_info["requirements"]
                for requirement in requirements:
                    requirment_name = os.path.basename(urllib.parse.unquote(requirement))
                    print(f"Install requirement {requirment_name}")
                    ret = run_commandline(["wget", requirement, "-O", os.path.join(DOWNLOAD_DIR, requirment_name)])
                    if ret != 0:
                        print(f"Failed to get requirement file{requirment_name}")
                        exit(4)
                    if requirment_name.endswith(".zip"):
                        ret = run_commandline(["unzip", "-o", os.path.join(DOWNLOAD_DIR, requirment_name), "-d", "/usr/lib/"])
                        if ret != 0:
                            print(f"Failed to unzip requirement {requirment_name}")
                            exit(5)
                    elif requirment_name.endswith(".deb"):
                        ret = run_commandline(["dpkg", "-i", os.path.join(DOWNLOAD_DIR, requirment_name)])
                        if ret != 0:
                            print(f"Failed to install requirement {requirment_name}")
                            exit(6)
                    else:
                        print(f"Non-implemented requirement extension for {requirment_name}")
                        exit(7)
                ret = run_commandline(["ldconfig"])
                if ret != 0:
                    print(f"Error in reloading libraries - keep installing")

            if args.safety:
                safety = ver_info["safety"]
                safety_appname = os.path.basename(urllib.parse.unquote(safety))
                print(f"Download SafetyBoard App from {safety}")
                ret = run_commandline(["wget", safety, "-O", UPDATE_FILE_DEFAULT])
                if ret != 0:
                    print(f"Failed to download SafetyBoard App")
                    exit(8)

                print(f"Install SafetyBoard App")
                ret = run_commandline(["python3", os.path.join(PYTHON_MIDDLEWARE_DIR, "bbb_updater.py")])
                if ret != 0:
                    print(f"Failed to install SafetyBoard App (exit code={ret})")
                    exit(9)

        print("Now call UpdateIndySW")
