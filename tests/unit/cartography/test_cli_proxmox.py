from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

import cartography.cli


@pytest.mark.parametrize(
    ("extra_args", "expected"),
    [([], False), (["--proxmox-detailed-reads"], True)],
)
def test_proxmox_detailed_reads_cli_config(extra_args, expected):
    # Arrange
    cli = cartography.cli.CLI(MagicMock(), "test")

    # Act
    with patch("cartography.sync.run_with_config", return_value=0) as run:
        exit_code = cli.main(
            [
                "--neo4j-uri",
                "bolt://localhost:7687",
                "--selected-modules",
                "proxmox",
                "--proxmox-host",
                "pve.example.com",
                *extra_args,
            ]
        )

    # Assert - the extra per-item reads are off unless asked for
    assert exit_code == 0
    config = run.call_args.args[1]
    assert config.proxmox_detailed_reads is expected
