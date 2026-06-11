// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {MintRouter} from "../src/MintRouter.sol";

contract DeployMintRouter is Script {
    // Base mainnet defaults — override with VAULT/USDC/VESC env vars for testnet deploys
    address constant VAULT = 0x50F50cF026837aB49f337927d2B3269a7DEDbc60;
    address constant USDC  = 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913;
    address constant VESC  = 0xDc83741833CA8e140137a9A63B23970d55205BA0;

    function run() external {
        address vault = vm.envOr("VAULT", VAULT);
        address usdc  = vm.envOr("USDC", USDC);
        address vesc  = vm.envOr("VESC", VESC);

        vm.startBroadcast();
        MintRouter router = new MintRouter(vault, usdc, vesc);
        vm.stopBroadcast();

        console.log("MintRouter deployed:", address(router));
        console.log("  vault:", vault);
        console.log("  usdc: ", usdc);
        console.log("  vesc: ", vesc);
    }
}
