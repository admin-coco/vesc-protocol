// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Script} from "forge-std/Script.sol";
import {VESCVault} from "../src/VESCVault.sol";

contract UpgradeVESC is Script {
    // Address of the existing ERC1967Proxy
    address constant PROXY = address(0); // TODO: set before running

    function run() external {
        require(PROXY != address(0), "Set PROXY address before upgrading");

        vm.startBroadcast();

        // Deploy new implementation
        VESCVault newImpl = new VESCVault();

        // Upgrade proxy to new implementation (no re-initialization needed)
        VESCVault(PROXY).upgradeToAndCall(address(newImpl), "");

        vm.stopBroadcast();
    }
}
