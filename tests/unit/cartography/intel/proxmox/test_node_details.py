"""
Unit tests for the Proxmox node details transforms.
"""

from cartography.intel.proxmox import node_details
from tests.data.proxmox import node_details as data

CLUSTER = "test-cluster"
NODE = "node1"


def _disks():
    return node_details.transform_disks(data.MOCK_DISKS, data.MOCK_SMART, NODE, CLUSTER)


def test_transform_disks_merges_smart_values():
    disks = {d["devpath"]: d for d in _disks()}

    sda = disks["/dev/sda"]
    assert sda["id"] == "test-cluster/node1:/dev/sda"
    assert sda["node_id"] == "test-cluster/node1"
    assert sda["name"] == "sda"
    assert sda["type"] == "ssd"
    assert sda["gpt"] is True
    assert sda["mounted"] is False
    assert sda["smart_type"] == "ata"
    assert sda["smart_health"] == "PASSED"
    assert sda["power_on_hours"] == 12045
    assert sda["reallocated_sectors"] == 0
    assert sda["percentage_used"] == 2
    # 194 is missing, so the airflow temperature (190) is used
    assert sda["temperature"] == 34

    assert disks["/dev/sdb"]["temperature"] == 36
    assert disks["/dev/sdb"]["reallocated_sectors"] == 8

    nvme = disks["/dev/nvme0n1"]
    assert nvme["name"] == "nvme0n1"
    assert nvme["smart_type"] == "text"
    assert nvme["power_on_hours"] == 8760
    assert nvme["percentage_used"] == 3
    assert nvme["temperature"] == 41
    assert nvme["reallocated_sectors"] is None

    assert disks["/dev/sdc"]["power_on_hours"] is None


def test_parse_smart_data_sas_text():
    smart = {
        "health": "OK",
        "type": "text",
        "text": (
            "Current Drive Temperature:     30 C\n"
            "Accumulated power on time, hours:minutes 41234:12\n"
            "Percentage used endurance indicator: 1%\n"
            "Elements in grown defect list: 4\n"
        ),
    }

    result = node_details.parse_smart_data(smart)

    assert result == {
        "smart_type": "text",
        "smart_health": "OK",
        "power_on_hours": 41234,
        "percentage_used": 1,
        "reallocated_sectors": 4,
        "temperature": 30,
    }


def test_parse_smart_data_empty():
    result = node_details.parse_smart_data({})
    assert result["smart_health"] is None
    assert result["power_on_hours"] is None


def test_match_device_to_disk():
    disks = _disks()
    by_name = {d["name"]: d["id"] for d in disks}

    assert node_details.match_device_to_disk("/dev/sda", disks) == by_name["sda"]
    assert node_details.match_device_to_disk("sdc1", disks) == by_name["sdc"]
    assert (
        node_details.match_device_to_disk("/dev/nvme0n1p3", disks) == by_name["nvme0n1"]
    )
    assert (
        node_details.match_device_to_disk("wwn-0x5002538f4210dcba-part3", disks)
        == by_name["sdb"]
    )
    assert (
        node_details.match_device_to_disk(
            "/dev/disk/by-id/ata-Samsung_SSD_870_EVO_1TB_S6PTNM0R123456-part3",
            disks,
        )
        == by_name["sda"]
    )
    assert (
        node_details.match_device_to_disk("nvme-eui.0025385791b0abcd", disks)
        == by_name["nvme0n1"]
    )
    assert node_details.match_device_to_disk("/dev/disk/by-uuid/1234", disks) is None
    assert node_details.match_device_to_disk(None, disks) is None


def test_match_device_to_disk_does_not_treat_letters_as_partitions():
    disks = [
        {"id": "a", "name": "sda"},
        {"id": "b", "name": "nvme0n1"},
    ]
    # sdap1 is the first partition of disk sdap, not a partition of sda
    assert node_details.match_device_to_disk("sdap1", disks) is None
    # a disk name ending with a digit needs the p separator
    assert node_details.match_device_to_disk("nvme0n12", disks) is None


def test_transform_zfs_pools():
    pools = node_details.transform_zfs_pools(
        data.MOCK_ZFS_POOLS,
        data.MOCK_ZFS_POOL_DETAILS,
        _disks(),
        NODE,
        CLUSTER,
    )

    assert len(pools) == 1
    pool = pools[0]
    assert pool["id"] == "test-cluster/node1:zfs:rpool"
    assert pool["state"] == "DEGRADED"
    assert pool["errors"] == "No known data errors"
    # the empty spares section is not a device
    assert pool["member_devices"] == [
        "ata-Samsung_SSD_870_EVO_1TB_S6PTNM0R123456-part3",
        "wwn-0x5002538f4210dcba-part3",
    ]
    assert pool["degraded_devices"] == ["wwn-0x5002538f4210dcba-part3"]
    assert pool["disk_ids"] == [
        "test-cluster/node1:/dev/sda",
        "test-cluster/node1:/dev/sdb",
    ]


def test_transform_lvm():
    vgs = node_details.transform_lvm_volume_groups(
        data.MOCK_LVM, _disks(), NODE, CLUSTER
    )
    assert vgs == [
        {
            "id": "test-cluster/node1:lvm:pve",
            "cluster_id": CLUSTER,
            "node_name": NODE,
            "node_id": "test-cluster/node1",
            "name": "pve",
            "size": 999653638144,
            "free": 16106127360,
            "physical_volumes": ["/dev/nvme0n1p3"],
            "disk_ids": ["test-cluster/node1:/dev/nvme0n1"],
        },
    ]

    thin = node_details.transform_lvm_thin_pools(data.MOCK_LVM_THIN, NODE, CLUSTER)
    assert thin[0]["id"] == "test-cluster/node1:lvmthin:pve/data"
    assert thin[0]["volume_group_id"] == "test-cluster/node1:lvm:pve"


def test_transform_managed_directories():
    dirs = node_details.transform_managed_directories(
        data.MOCK_DIRECTORIES,
        _disks(),
        NODE,
        CLUSTER,
    )
    assert dirs[0]["id"] == "test-cluster/node1:directory:/mnt/pve/backup"
    assert dirs[0]["disk_ids"] == ["test-cluster/node1:/dev/sdc"]


def test_transform_packages():
    packages = {
        p["name"]: p
        for p in node_details.transform_packages(
            data.MOCK_PACKAGE_VERSIONS,
            NODE,
            CLUSTER,
        )
    }
    assert packages["proxmox-ve"]["running_kernel"] == "6.14.8-2-pve"
    assert packages["pve-manager"]["manager_version"] == "9.0.10"
    assert packages["qemu-server"]["old_version"] == "9.0.21"
    assert packages["qemu-server"]["id"] == "test-cluster/node1:package:qemu-server"


def test_transform_apt_repositories():
    repos = node_details.transform_apt_repositories(
        data.MOCK_APT_REPOSITORIES,
        NODE,
        CLUSTER,
    )
    assert [(r["id"], r["enabled"]) for r in repos] == [
        (
            "test-cluster/node1:apt:/etc/apt/sources.list.d/pve-enterprise.sources:0",
            False,
        ),
        ("test-cluster/node1:apt:/etc/apt/sources.list:0", True),
        ("test-cluster/node1:apt:/etc/apt/sources.list:1", True),
    ]
    assert repos[2]["components"] == ["pve-no-subscription"]

    summary = node_details.transform_apt_repository_summary(data.MOCK_APT_REPOSITORIES)
    assert summary == {
        "enterprise_repo_enabled": False,
        "no_subscription_repo_enabled": True,
        "test_repo_enabled": None,
        "enabled_standard_repos": ["ceph-squid-no-subscription", "no-subscription"],
        "apt_repository_errors": [
            "/etc/apt/sources.list.d/broken.list: malformed entry",
        ],
    }


def test_transform_subscription_never_keeps_secrets():
    sub = node_details.transform_subscription(data.MOCK_SUBSCRIPTION, NODE, CLUSTER)

    assert sub["status"] == "active"
    assert sub["level"] == "c"
    assert sub["nextduedate"] == "2027-01-01"
    assert sub["key_suffix"] == "89ab"
    assert "key" not in sub
    assert "signature" not in sub
    assert "serverid" not in sub
    assert "SIGNATURE-DO-NOT-STORE" not in sub.values()
    assert data.MOCK_SUBSCRIPTION["key"] not in sub.values()

    short = node_details.transform_subscription(
        {"status": "notfound", "key": "abcd"}, NODE, CLUSTER
    )
    assert short["key_suffix"] is None


def test_transform_node_config():
    config = node_details.transform_node_config(
        data.MOCK_NODE_CONFIG,
        data.MOCK_NODE_DNS,
        data.MOCK_NODE_TIME,
        data.MOCK_APT_REPOSITORIES,
        NODE,
        CLUSTER,
    )

    assert config["id"] == "test-cluster/node1:config"
    assert config["description"] == "Rack 3, unit 12"
    assert config["wakeonlan_mac"] == "aa:bb:cc:dd:ee:ff"
    assert config["wakeonlan_bind_interface"] == "eno1"
    assert config["wakeonlan_broadcast_address"] is None
    assert config["ballooning_target"] == 75
    assert config["acme_account"] == "prod"
    assert config["acme_domains"] == ["node1.example.com", "node1-alt.example.com"]
    assert config["dns_servers"] == ["10.0.0.53", "1.1.1.1"]
    assert config["dns_search"] == "example.com"
    assert config["timezone"] == "Europe/Rome"
    assert config["no_subscription_repo_enabled"] is True
    assert "digest" not in config


def test_transform_services():
    services = node_details.transform_services(data.MOCK_SERVICES, NODE, CLUSTER)
    assert services[1] == {
        "id": "test-cluster/node1:service:corosync",
        "cluster_id": CLUSTER,
        "node_name": NODE,
        "node_id": "test-cluster/node1",
        "name": "corosync",
        "service": "corosync",
        "description": "Corosync Cluster Engine",
        "state": "dead",
        "active_state": "inactive",
        "unit_state": "disabled",
    }


def test_transform_pci_devices():
    devices = node_details.transform_pci_devices(
        data.MOCK_PCI_DEVICES,
        data.MOCK_PCI_MDEV_TYPES,
        NODE,
        CLUSTER,
    )
    gpu, nic = devices
    assert gpu["id"] == "test-cluster/node1:pci:0000:01:00.0"
    assert gpu["pci_class"] == "0x030000"
    assert gpu["iommu_group"] == 14
    assert gpu["mdev"] is True
    assert gpu["mdev_types"] == ["nvidia-222", "nvidia-223"]
    assert gpu["mdev_available"] == 24
    assert nic["mdev"] is False
    assert nic["mdev_types"] is None
    assert nic["mdev_available"] is None
