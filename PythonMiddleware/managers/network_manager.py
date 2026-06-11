import subprocess
import socket
import re
import yaml
import os
import time
import configparser
import select

class NetworkManager:
    IPS_FIXED = ["192.168.7.1", "192.168.50.2"]

    @classmethod
    def list_interfaces(cls):
        try:
            skip_prefixes = ["lo", "docker", "veth", "br-", "virbr", "tun", "tap", "ecdbg", "rmnet", "ifb"]

            result = subprocess.check_output(["ip", "-o", "link", "show"]).decode()
            interfaces_all = [line.split(":")[1].strip() for line in result.splitlines()]
            interfaces = [iface for iface in interfaces_all
                          if not any(iface.startswith(prefix) for prefix in skip_prefixes)]
            return sorted(interfaces)
        except subprocess.CalledProcessError:
            return []

    @classmethod
    def get_ip_and_netmask(cls, interface):
        try:
            result = subprocess.check_output(["ip", "addr", "show", interface]).decode()
            ip_match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/(\d+)", result)
            if ip_match:
                ip = ip_match.group(1)
                cidr = int(ip_match.group(2))
                netmask = socket.inet_ntoa(((1 << 32) - (1 << 32 >> cidr)).to_bytes(4, 'big'))
                return ip, netmask
        except subprocess.CalledProcessError:
            pass
        return None, None

    @classmethod
    def get_mac_address(cls, interface):
        try:
            result = subprocess.check_output(["cat", f"/sys/class/net/{interface}/address"]).decode()
            return result.strip()
        except subprocess.CalledProcessError:
            return None

    @classmethod
    def get_gateways_by_interface(cls):
        gateways = {}
        try:
            result = subprocess.check_output(["ip", "route", "show"]).decode()
            for line in result.splitlines():
                if line.startswith("default"):
                    match = re.search(r"default via (\d+\.\d+\.\d+\.\d+) dev (\w+)", line)
                    if match:
                        gw_ip = match.group(1)
                        iface = match.group(2)
                        gateways[iface] = gw_ip
        except subprocess.CalledProcessError:
            pass
        return gateways

    @classmethod
    def get_dns_by_resolv_conf(cls):
        servers = []
        try:
            with open("/etc/resolv.conf", "r") as f:
                for line in f:
                    if line.startswith("nameserver"):
                        servers.append(line.strip().split()[1])
        except Exception:
            pass
        return servers

    @classmethod
    def is_using_dhcp(cls, interface):
        version = cls.get_ubuntu_version()
        if version is None:
            return None

        if version < 18.0:
            # Check /etc/network/interfaces
            try:
                pattern = re.compile(rf'^\s*iface\s+{interface}\s+inet\s+(\S+)', re.IGNORECASE)
                with open("/etc/network/interfaces") as f:
                    lines = f.readlines()
                in_block = False
                for line in lines:
                    match = pattern.match(line)
                    if match is not None:
                        method = match.group(1)
                        if method == 'dhcp':
                            return True
                        elif method == 'static':
                            return False
                        else:
                            return None
                return cls.is_nmcli_with_dhcp(interface)
            except Exception as e:
                print(f"Exception reading dhcp for {interface}: {e}")
        else:
            # Check /etc/netplan/*.yaml
            try:
                for file in os.listdir("/etc/netplan"):
                    if file.endswith(".yaml") or file.endswith(".yml"):
                        with open(f"/etc/netplan/{file}", "r") as f:
                            config = yaml.safe_load(f)
                            ethernets = config.get("network", {}).get("ethernets", {})
                            if interface in ethernets:
                                return ethernets[interface].get("dhcp4", None)
            except Exception:
                print(f"Exception reading dhcp for {interface}: {e}")
        return None

    @classmethod
    def print_full_network_info(cls):
        interfaces = cls.list_interfaces()
        gateways = cls.get_gateways_by_interface()
        dns = cls.get_dns_by_resolv_conf()

        for iface in interfaces:
            ip, netmask = cls.get_ip_and_netmask(iface)
            mac = cls.get_mac_address(iface)
            gateway = gateways.get(iface)
            dhcp = cls.is_using_dhcp(iface)

            print(f"=== 인터페이스: {iface} ===")
            print(f"MAC 주소       : {mac}")
            print(f"IP 주소        : {ip if ip else '없음'}")
            print(f"서브넷 마스크  : {netmask if netmask else '없음'}")
            print(f"게이트웨이     : {gateway if gateway else '없음'}")
            print(f"DHCP 사용 여부 : {'예' if dhcp else ('아니오' if dhcp == False else '미정')}")
        print("==========================")
        print(f"DNS 서버       : {', '.join(dns) if dns else '없음'}")

    @classmethod
    def get_ubuntu_version(cls):
        try:
            with open("/etc/os-release", "r") as f:
                for line in f:
                    if line.startswith("VERSION_ID="):
                        version_str = line.strip().split("=")[1].strip('"')
                        return float(version_str)
        except Exception as e:
            print(f"Ubuntu 버전 확인 실패: {e}")
        return None

    @classmethod
    def pick_dns_interface(cls):
        ifaces = cls.list_interfaces()
        if len(ifaces) > 0:
            return ifaces[0]
        else:
            return None

    @classmethod
    def get_managed_interfaces(cls):
        try:
            output = subprocess.check_output(["nmcli", "-t", "-f", "DEVICE,STATE", "device"], universal_newlines=True)
            connected = []
            for line in output.strip().splitlines():
                parts = line.split(":")
                if len(parts) == 2 and parts[1] != "unmanaged":
                    connected.append(parts[0])
            return connected
        except Exception:
            return []

    @classmethod
    def find_matching_connection(cls, interface):
        """
        Try to find which system-connections config file is being used by this interface.
        Match priority: interface-name > mac-address > fallback to first matching candidate.
        """
        con_dir = "/etc/NetworkManager/system-connections"
        iface_mac = cls.get_mac_address(interface)
        if not iface_mac:
            return None
        exact_match = None
        mac_match = None
        fallback = None
        for fname in os.listdir(con_dir):
            fpath = os.path.join(con_dir, fname)
            try:
                config = configparser.ConfigParser()
                config.read(fpath)
                if "connection" in config:
                    if config["connection"].get("interface-name") == interface:
                        exact_match = fpath
                        break  # strongest match
                if "ethernet" in config:
                    mac = config["ethernet"].get("mac-address", "").lower()
                    if mac == iface_mac:
                        mac_match = fpath
                if not fallback:
                    fallback = fpath  # first candidate seen
            except Exception:
                continue
        return exact_match or mac_match or fallback

    @classmethod
    def is_dhcp_method_in_connection_file(cls, filepath):
        try:
            config = configparser.ConfigParser()
            config.read(filepath)
            method = config.get("ipv4", "method", fallback=None)
            return method == "auto"
        except Exception as e:
            print(f"is_dhcp_method_in_connection_file exception {e}")
            return False

    @classmethod
    def is_nmcli_with_dhcp(cls, interface):
        managed = cls.get_managed_interfaces()
        if interface not in managed:
            return False  # interface is not managed by network manager
        matched_conf = cls.find_matching_connection(interface)
        if not matched_conf:
            return False  # no configuration file found
        return cls.is_dhcp_method_in_connection_file(matched_conf)
    @classmethod
    def configure_interface(cls, interface, use_dhcp=True, ip=None, netmask=None, gateway=None):
        version = cls.get_ubuntu_version()
        if version is None:
            return 99

        if version < 18.0:
            ret = cls.configure_interfaces_file(interface, use_dhcp, ip, netmask, gateway)
            subprocess.run(f"ifdown {interface} && ifup {interface}", shell=True, check=True)
            return ret
        else:
            return cls.configure_netplan(interface, use_dhcp, ip, netmask, gateway)

    @classmethod
    def configure_dns(cls, dns):
        version = cls.get_ubuntu_version()
        if version is None:
            return 99

        dns_iface = cls.pick_dns_interface()
        if dns_iface is None:
            print(f"There is no network interface to set DNS")
            return 0

        if version < 18.0:
            ret = cls.configure_interfaces_file_dns(dns_iface, dns)
            subprocess.run(f"ifdown {dns_iface} && ifup {dns_iface}", shell=True, check=True)
            return ret
        else:
            return cls.configure_netplan_dns(dns_iface, dns)

    @classmethod
    def configure_interfaces_file(cls, interface, use_dhcp, ip, netmask, gateway):
        path = "/etc/network/interfaces"

        try:
            lines = []
            if os.path.exists(path):
                with open(path, "r") as f:
                    lines = f.readlines()

            new_block = [f"auto {interface}\n"]
            if use_dhcp:
                new_block.append(f"iface {interface} inet dhcp\n")
            else:
                if not all([ip, netmask]):
                    print("Static 설정 시 IP, Netmask, Gateway 필수")
                    return 1
                new_block.append(f"iface {interface} inet static\n")
                new_block.append(f"    address {ip}\n")
                new_block.append(f"    netmask {netmask}\n")
                if gateway:
                    new_block.append(f"    gateway {gateway}\n")

            in_block = False
            block_indent = 0
            in_dns = False
            dns_indent = 0
            block_lines = []
            filtered = []
            dns_lines = []
            for line in lines:
                if line.strip() == f"auto {interface}" or line.strip().startswith(f"iface {interface} "):
                    in_block = True
                    block_indent = len(line) - len(line.lstrip())
                elif in_block:
                    indent = len(line) - len(line.lstrip())
                    if ((indent <= block_indent)
                            or line.strip().startswith("auto")
                            or line.strip().startswith("iface")
                            or len(line.strip()) == 0
                    ):
                        in_block = False

                    if (dns_indent == 0) and (indent > block_indent):  # init dns_indent = first indent
                        dns_indent = indent

                    if line.strip().startswith(f"dns-nameservers"):
                        in_dns = True
                        dns_indent = indent
                    else:
                        if ((indent <= dns_indent)
                                or line.strip().startswith("auto")
                                or line.strip().startswith("iface")
                                or len(line.strip()) == 0
                        ):
                            in_dns = False

                if in_block:
                    if in_dns:
                        dns_lines.append(" "*dns_indent + f"{line.strip()}\n")
                    else:
                        block_lines.append(line)
                else:
                    filtered.append(line)

            result_lines = filtered + ["\n"] + new_block + dns_lines

            result_slim = []
            empty_line = False
            for line in result_lines:
                if((len(line.strip()) == 0) and ("\n" in line)):
                    if empty_line:
                        continue
                    else:
                        empty_line = True
                else:
                    empty_line = False
                result_slim.append(line)

            with open(path, "w") as f:
                f.writelines(result_slim)

            print(f"{path} 설정 완료")
            return 0

        except Exception as e:
            print(f"interfaces 파일 설정 실패: {e}")
            return 2

    @classmethod
    def configure_interfaces_file_dns(cls, interface, dns):
        path = "/etc/network/interfaces"
        try:
            lines = []
            if os.path.exists(path):
                with open(path, "r") as f:
                    lines = f.readlines()


            in_block = False
            block_indent = 0
            in_dns = False
            dns_indent = 0
            block_lines = []
            filtered = []
            dns_lines = []
            for line in lines:
                if line.strip() == f"auto {interface}" or line.strip().startswith(f"iface {interface} "):
                    in_block = True
                    block_indent = len(line) - len(line.lstrip())
                elif in_block:
                    indent = len(line) - len(line.lstrip())
                    if ((indent <= block_indent)
                            or line.strip().startswith("auto")
                            or line.strip().startswith("iface")
                            or len(line.strip()) == 0
                    ):
                        in_block = False

                    if (dns_indent == 0) and (indent > block_indent):  # init dns_indent = first indent
                        dns_indent = indent

                    if line.strip().startswith(f"dns-nameservers"):
                        in_dns = True
                        dns_indent = indent
                    else:
                        if ((indent <= dns_indent)
                                or line.strip().startswith("auto")
                                or line.strip().startswith("iface")
                                or len(line.strip()) == 0
                        ):
                            in_dns = False

                if in_block:
                    if in_dns:
                        dns_lines.append(" "*dns_indent + f"{line.strip()}\n")
                    else:
                        block_lines.append(line)
                else:
                    filtered.append(line)

            if len(block_lines) == 0:
                block_lines = [f"auto {interface}\n",
                               f"iface {interface} inet dhcp\n"]

            if dns_indent == 0:
                dns_indent = block_indent + 4

            result_lines = (filtered + ["\n"] +
                            block_lines + [" "*dns_indent + f"dns-nameservers {' '.join(dns)}\n"] + ["\n"])

            result_slim = []
            empty_line = False
            for line in result_lines:
                if((len(line.strip()) == 0) and ("\n" in line)):
                    if empty_line:
                        continue
                    else:
                        empty_line = True
                else:
                    empty_line = False
                result_slim.append(line)

            with open(path, "w") as f:
                    f.writelines(result_slim)

            print(f"DNS 설정 완료: {path}")
            return 0

        except Exception as e:
            print(f"interfaces DNS 설정 실패: {e}")
            return 4

    @classmethod
    def configure_netplan(cls, interface, use_dhcp, ip, netmask, gateway):
        path = "/etc/netplan/99-generated.yaml"
        try:
            if os.path.exists(path):
                with open(path, "r") as f:
                    config = yaml.safe_load(f)
            else:
                config = {
                    "network": {
                        "version": 2,
                        "renderer": "NetworkManager",
                        "ethernets": {}
                    }
                }

            ethernets = config.setdefault("network", {}).setdefault("ethernets", {})
            iface_cfg = {}

            if use_dhcp:
                iface_cfg["dhcp4"] = True
            else:
                if not all([ip, netmask]):
                    print("Static 설정 시 IP, Netmask 필수")
                    return 1
                cidr = sum(bin(int(x)).count("1") for x in netmask.split("."))
                iface_cfg["dhcp4"] = False
                iface_cfg["addresses"] = [f"{ip}/{cidr}"]
                if gateway:
                    iface_cfg["gateway4"] = gateway

            ethernets[interface] = iface_cfg

            with open(path, "w") as f:
                yaml.dump(config, f, default_flow_style=False)

            subprocess.run("netplan apply", shell=True, check=True)
            print(f"netplan 적용 완료: {path}")
            return 0
        except Exception as e:
            print(f"netplan 설정 실패: {e}")
            return 3

    @classmethod
    def configure_netplan_dns(cls, interface, dns):
        path = "/etc/netplan/99-generated.yaml"
        try:
            if not os.path.exists(path):
                print("netplan 파일 없음 - DNS 설정 불가")
                return 5

            with open(path, "r") as f:
                config = yaml.safe_load(f)

            ethernets = config.get("network", {}).get("ethernets", {})
            if interface not in ethernets:
                print(f"{interface} 설정이 netplan에 없음")
                return 6

            ethernets[interface]["nameservers"] = {"addresses": dns}

            with open(path, "w") as f:
                yaml.dump(config, f, default_flow_style=False)

            subprocess.run("netplan apply", shell=True, check=True)
            print("netplan DNS 설정 완료")
            return 0
        except Exception as e:
            print(f"netplan DNS 설정 실패: {e}")
            return 7

    @classmethod
    def check_connection_via_iface(cls, iface: str, target_ip: str, port: int = 80, timeout_ms: int = 200) -> bool:
        try:
            # 소켓 생성
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setblocking(False)  # 비차단 모드

            # 인터페이스 바인딩 (root 권한 필요)
            ifname = iface.encode('utf-8')
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, ifname)

            # 주소 설정
            addr = (target_ip, port)

            try:
                sock.connect(addr)
            except BlockingIOError:
                pass  # 예상된 동작 (non-blocking에서의 connect)

            # select로 쓰기 가능 여부 확인
            rlist, wlist, xlist = select.select([], [sock], [], timeout_ms / 1000.0)

            if sock in wlist:
                # 연결 성공 여부 확인
                err = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                sock.close()
                return err == 0
            else:
                sock.close()
                return False

        except Exception as e:
            print(f"check_connection_via_iface Exception: {e}")
            return False

if __name__ == "__main__":
    NetworkManager.print_full_network_info()
