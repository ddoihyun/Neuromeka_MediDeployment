import os
import json
import shutil
import datetime
import zipfile
from common.utils import load_json, write_json
from common.version import REFERENCE_POSTFIX

PYTHON_MIDDLEWARE_DIR = os.path.dirname(os.path.abspath(__file__))
DEPLOYMENT_DIR = os.path.abspath(os.path.join(PYTHON_MIDDLEWARE_DIR, os.pardir))
CONFIGURATION_DIR = os.path.normpath(os.path.join(DEPLOYMENT_DIR, '../IndyConfigurations'))
UPDATE_RULE_PATH = os.path.join(PYTHON_MIDDLEWARE_DIR, 'update_rule.json')
VERSION_RECORD_PATH = os.path.join(PYTHON_MIDDLEWARE_DIR, 'current_version.json')
KILL_TASKS_PATH = os.path.join(DEPLOYMENT_DIR, "killTasks.sh")

def copy_overwrite_tree(src, dst):
    if not os.path.exists(dst):
        os.makedirs(dst)

    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            copy_overwrite_tree(s, d)
        else:
            shutil.copy2(s, d)


def delete_key_recursively(data, key_to_delete):
    if isinstance(data, dict):
        if key_to_delete in data:
            del data[key_to_delete]
            print(f"Deleted key: {key_to_delete}")
        for key, value in data.items():
            delete_key_recursively(value, key_to_delete)
    elif isinstance(data, list):
        for item in data:
            delete_key_recursively(item, key_to_delete)


def delete_key_in_json_files(root_path, file_name, key_to_delete):
    for root, dirs, files in os.walk(root_path):
        for filename in files:
            if file_name == filename:
                filepath = os.path.join(root, filename)
                with open(filepath, 'r') as read_file:
                    json_data = json.load(read_file)
                delete_key_recursively(json_data, key_to_delete)
                with open(os.path.join(root, file_name), 'w') as file:
                    json.dump(json_data, file, indent=4)


##
# @brief insert key value
# @param overwrite  put new value even if already exists
def insert_key_value(target_json, key_value_dict, key, overwrite: bool):
    if isinstance(target_json, dict):
        current_level = target_json
        key_list = key.split('.')
        print(key_list)        
        for key in key_list[:-1]:
            if key not in current_level:
                current_level[key] = {}  # new dict
            current_level = current_level[key]
        key = key_list[-1]  # last key
        if (key not in current_level) or overwrite:  # put if empty or overwrite
            current_level[key] = key_value_dict
        print(current_level)


##
# @brief look for file name and insert key value
# @param overwrite  put new value even if already exists
def add_key_in_json_files(file_name, key_to_add, overwrite: bool):
    filepath = os.path.join(DEPLOYMENT_DIR, file_name)
    ref_filepath = get_reference_filepath(filepath)
    with open(ref_filepath, 'r') as read_file:
        json_data = json.load(read_file)

    update_key, update_value = find_key_with_path(json_data, key_to_add)
    print(update_value)

    if os.path.isfile(filepath):
        print(f"file to add key is there: {filepath}")
        with open(filepath, 'r') as read_file:
            json_data = json.load(read_file)
        insert_key_value(json_data, update_value, update_key, overwrite)
        print(json_data)
        with open(filepath, 'w') as file:
            print(file)
            json.dump(json_data, file, indent=4)
    else:
        print(f"file to add key is not there - skip for file {filepath}")


def get_key_data_in_json(json_data, key_name):
    if isinstance(json_data, dict):
        for key, value in json_data.items():
            if key == key_name:
                return value
            elif isinstance(value, dict):
                result = get_key_data_in_json(value, key_name)
                if result is not None:
                    return result
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        result = get_key_data_in_json(item, key_name)
                        if result is not None:
                            return result
    return None


def extract_key_value(data, target_key, parent_key=''):
    if isinstance(data, dict):
        for key, value in data.items():
            full_key = f"{parent_key}.{key}" if parent_key else key
            if full_key == target_key:
                return {key: value}
            elif isinstance(value, dict):
                result = extract_key_value(value, target_key, full_key)
                if result:
                    print("result: ", result)
                    return {key: result[key]}
    return None


def find_key_with_path(data, target_key, current_path=""):
    if isinstance(data, dict):
        for key, value in data.items():
            new_path = f"{current_path}.{key}" if current_path else key  # 경로 갱신
            if key == target_key:
                return new_path, value  # 경로와 값 반환
            elif isinstance(value, dict):
                result = find_key_with_path(value, target_key, new_path)
                if result is not None:
                    return result
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        result = find_key_with_path(item, target_key, f"{new_path}[{i}]")
                        if result is not None:
                            return result
    return None

def get_reference_filepath(filepath):
    filepath_split = filepath.split(".")
    filepath_split[-2] = filepath_split[-2]+f"-{REFERENCE_POSTFIX}"
    ref_filepath = ".".join(filepath_split)
    return ref_filepath


##
# @brief    process downloaded update file
# @remark   1. new IndyDeployment/*.json files are moved to  IndyDeployment/*-new.json \n
#           2. Old IndyConfigurations folder is backed up to IndyConfigurations-backup-YYYYMMDDHHMMSS.json \n
#           3. Old IndyConfigurations folder is copied back to the applied folder, except for "Default" folder \n
#           Finally, Old configurations files are used but only "Default" folder is new,
#           and IndyDeployment/*-new.json are created \n
#           [IMPORTANT NOTE] this part is run by old indy_run.py on update. So this part should be backward-compatible
def process_update_file(sw_update_file):
    if os.path.isfile(sw_update_file):
        print("SW Update: " + sw_update_file)
        now_str = str(datetime.datetime.now().strftime('%Y%m%d%H%M%S'))
        now_bak_str = f'-backup-{now_str}'

        # Make backup for deployment json -> -backup-YYYYMMDDHHMMSS.json
        configs_to_recover = []
        for fname in os.listdir(DEPLOYMENT_DIR):
            if fname.endswith(".json") and (fname.find("backup") < 0) and (fname.find("new") < 0):
                configs_to_recover.append(fname)
                bak_name = fname[:-5] + now_bak_str + ".json"
                shutil.copy(os.path.join(DEPLOYMENT_DIR, fname),
                            os.path.join(DEPLOYMENT_DIR, bak_name))

        # Unzip new files
        with zipfile.ZipFile(sw_update_file, 'r') as zip_ref:
            print("Update path: " + str(DEPLOYMENT_DIR))
            zip_ref.extractall(path=DEPLOYMENT_DIR)
        os.remove(sw_update_file)

        ## Recover old deployment json (unzipped->new, bak->applied, remove bak files)
        # This old file recovery and new file backup is deprecated but cannot be removed for backward compatibility
        # Just Ignore and DO NOT USE "*-new.json" format for a filename - it can be unintentionally removed here.
        for fname in configs_to_recover:
            bak_name = fname[:-5] + now_bak_str + ".json"
            new_name = fname[:-5] + "-new.json"
            shutil.copy(os.path.join(DEPLOYMENT_DIR, fname),
                        os.path.join(DEPLOYMENT_DIR, new_name))
            shutil.copy(os.path.join(DEPLOYMENT_DIR, bak_name),
                        os.path.join(DEPLOYMENT_DIR, fname))
            os.remove(os.path.join(DEPLOYMENT_DIR, bak_name))

        # Recover old configurations (new<-overwritten, bak->applied, except default new default applied)
        update_config_path_src = os.path.join(DEPLOYMENT_DIR, 'IndyConfigurations')
        update_config_path_tar = os.path.normpath(os.path.join(DEPLOYMENT_DIR, '../IndyConfigurations'))
        if os.path.isdir(update_config_path_src):
            path_bak = None
            if os.path.isdir(update_config_path_tar):  # Backup original configs
                path_bak = update_config_path_tar + now_bak_str
                shutil.copytree(update_config_path_tar, path_bak)
            copy_overwrite_tree(update_config_path_src, update_config_path_tar)  # Move new configs - copy src
            shutil.rmtree(update_config_path_src)  # Move new configs - remove src
            if path_bak is not None:
                bak_folders = os.listdir(path_bak)
                for folder_name in bak_folders:  # Recover original configs, except for Default
                    if folder_name != "Default":
                        copy_overwrite_tree(os.path.join(path_bak, folder_name),
                                            os.path.join(update_config_path_tar, folder_name))


def install_and_reboot():
    # install and reboot
    os.system(f"nohup bash -c 'bash {os.path.join(DEPLOYMENT_DIR, 'install', 'install.sh')}; sudo reboot' &")


##
# @class ConfigUpdater
# @remark   Update Sequence: \n
# 1. (middleware) download zip file from Conty, exit middleware with EXIT_UPDATE code \n
# 2. (indy_run) EXIT_UPDATE code detected \n
# 3. (indy_run) process_update_file: Keep all other config files but use new Default folder.
#                                    `IndyDeployment/*-new.json` files are generated \n
# 4. (indy_run) Restart middleware, ProcessManager \n
# 5. (middleware) update_configs: Apply update_rule.json to `IndyDeployment/*.json` and `install.sh`, reboot \n
# 6. After reboot, UDEVMonitor starts all processes
# 7. (JsonConfigManager): Load Json parameters as defined for each variables (use default or history if needed)
class ConfigUpdater:
    def __init__(self, cur_version, deploy_file_name):
        self.version = cur_version
        self.deploy_file_name = deploy_file_name

    ##
    # @brief    update configs assuming assuming process_update_file() is called previously \n
    #           Assume only "Default" folder is new, and IndyDeployment/*-new.json are created
    @classmethod
    def update_configs(cls):
        print("update_configs")
        with open(UPDATE_RULE_PATH, 'r') as file:
            special_rule = json.load(file)
        for add_file_name in special_rule["AddFile"]:  # Add only if not exist already
            add_file_path = os.path.join(DEPLOYMENT_DIR, add_file_name)
            ref_file_path = get_reference_filepath(add_file_path)
            if os.path.isfile(ref_file_path):
                if not os.path.isfile(add_file_path):
                    shutil.copy(ref_file_path, add_file_path)
                    print("added file : ", add_file_path)
            else:
                print("update failed - no reference file to add: ", add_file_path)
        for overite_file_name in special_rule["OverwriteFile"]:  # overwrite existing file
            overite_file_path = os.path.join(DEPLOYMENT_DIR, overite_file_name)
            ref_file_path = get_reference_filepath(overite_file_path)
            if os.path.isfile(ref_file_path):
                shutil.copy(ref_file_path, overite_file_path)
                print("overwrite success : ", overite_file_name)
            else:
                print("update failed - no reference file to overwrite: ", overite_file_name)
        for delete_key_file in special_rule["DeleteKey"]:  # Delete Key - only this works for IndyConfigurations
            for delete_key_name in special_rule["DeleteKey"][delete_key_file]:
                delete_key_in_json_files(DEPLOYMENT_DIR, delete_key_file, delete_key_name)
                delete_key_in_json_files(CONFIGURATION_DIR, delete_key_file, delete_key_name)
        for add_key_file in special_rule["AddKey"]:  # Add Key if not exists
            for add_key_name in special_rule["AddKey"][add_key_file]:
                add_key_in_json_files(add_key_file, add_key_name, False)
        for overwrite_key_file in special_rule["OverwriteKey"]:  # Overwrite Key
            for overwrite_key_name in special_rule["OverwriteKey"][overwrite_key_file]:
                add_key_in_json_files(overwrite_key_file, overwrite_key_name, True)
        return True

    def check_and_update(self):
        version_data = {"cur_version": self.version}
        version_old = load_json(VERSION_RECORD_PATH)
        if ((version_old is None)
                or ("cur_version" not in version_old)
                or (version_old["cur_version"] != self.version)):
            files = [f for f in os.listdir(DEPLOYMENT_DIR) if f.endswith(f'-{REFERENCE_POSTFIX}.json')]  # new files
            if len(files) > 0:  # if reference files exist
                if self.update_configs():
                    for file in files:
                        delete_path = os.path.join(DEPLOYMENT_DIR, file)
                        if os.path.exists(delete_path):
                            os.remove(delete_path)
                            print(f"Removed file: {delete_path}")
            # write new version
            write_json(VERSION_RECORD_PATH, version_data)
            return True
        return False

    def update_kill_tasks(self):
        # load kill_names in killTasks.sh
        kill_names = []
        killtask_lines = []
        with open(KILL_TASKS_PATH, mode='r') as killFile:
            while True:
                content = killFile.readline()
                killtask_lines.append(content)
                if not content:
                    break
                contentSplit = content.split(" ")
                if "killall" in contentSplit:
                    kill_names.append(contentSplit[-1].replace("\n", ""))

        # load indyDeploy.json
        # for task in indyDeploy.json
        #   check if task name is in killTasks
        deploy_config = load_json(os.path.join(DEPLOYMENT_DIR, self.deploy_file_name))
        names_to_add = []
        if deploy_config is not None:
            if "RTTasks" in deploy_config:
                for task_name, task_config in deploy_config["RTTasks"].items():
                    if ("Enabled" in task_config) and task_config["Enabled"]:
                        if task_name not in kill_names:
                            names_to_add.append(task_name)
            if "NonRTTasks" in deploy_config:
                for task_name, task_config in deploy_config["NonRTTasks"].items():
                    if ("Enabled" in task_config) and task_config["Enabled"]:
                        if task_name not in kill_names:
                            names_to_add.append(task_name)

        # append kill commands to killTasks
        if len(names_to_add) > 0:
            LAST_LINE = 'echo "killTasks Done"'
            names_added = False
            print(f"Update {KILL_TASKS_PATH} with {names_to_add}")
            with open(KILL_TASKS_PATH, mode='w') as killFile:
                for line in killtask_lines:
                    if LAST_LINE in line:
                        for task_name in names_to_add:
                            killFile.write(f"sudo killall -9 {task_name}\n")
                        names_added = True
                    killFile.write(line)
                if not names_added:
                    for task_name in names_to_add:
                        killFile.write(f"\nsudo killall -9 {task_name}")
                    killFile.write(f"\n{LAST_LINE}")
