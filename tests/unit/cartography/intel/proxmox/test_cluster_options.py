"""
Tests for the Proxmox cluster options transform.
"""

from cartography.intel.proxmox.cluster import transform_cluster_options
from tests.data.proxmox.cluster import MOCK_CLUSTER_OPTIONS


def test_transform_cluster_options_flattens_parsed_property_strings():
    """The API returns migration, bwlimit and next-id as objects; only scalars are kept."""
    result = transform_cluster_options(MOCK_CLUSTER_OPTIONS)

    assert result["migration_type"] == "secure"
    assert result["migration_network"] == "192.168.1.0/24"
    assert result["migration_bandwidth_limit"] == 102400
    assert result["next_id_lower"] == 100
    assert result["next_id_upper"] == 999999999
    assert result["keyboard"] == "en-us"
    for value in result.values():
        assert not isinstance(value, dict)


def test_transform_cluster_options_accepts_property_strings():
    """A property string, or a bare default-key value, is parsed the same way."""
    result = transform_cluster_options(
        {
            "migration": "secure",
            "bwlimit": "migration=2048,default=4096",
            "next-id": "lower=1000,upper=2000",
        },
    )

    assert result["migration_type"] == "secure"
    assert result["migration_network"] is None
    assert result["migration_bandwidth_limit"] == 2048
    assert result["next_id_lower"] == 1000
    assert result["next_id_upper"] == 2000


def test_transform_cluster_options_without_options():
    """Unset options leave every derived field empty."""
    assert transform_cluster_options({}) == {}
    result = transform_cluster_options({"keyboard": "it"})
    assert result["migration_type"] is None
    assert result["migration_bandwidth_limit"] is None
    assert result["next_id_lower"] is None
