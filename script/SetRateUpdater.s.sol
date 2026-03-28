// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Script} from "forge-std/Script.sol";
import {VESCVault} from "../src/VESCVault.sol";

contract SetRateUpdater is Script {
    address constant PROXY       = 0x50F50cF026837aB49f337927d2B3269a7DEDbc60;
    address constant NEW_UPDATER = 0x01210B4069C16C03c701981715F79d17D78c1877;

    function run() external {
        vm.startBroadcast();
        VESCVault(PROXY).setRateUpdater(NEW_UPDATER);
        vm.stopBroadcast();
    }
}
