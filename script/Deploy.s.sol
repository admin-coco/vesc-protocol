// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Script} from "forge-std/Script.sol";
import {ERC1967Proxy} from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";
import {VESCToken} from "../src/VESCToken.sol";
import {VESCVault} from "../src/VESCVault.sol";

contract DeployVESC is Script {
    // Base mainnet USDC
    address constant USDC = 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913;

    // Base mainnet USDT — approved as rescue token for USDC blacklist emergency
    address constant USDT = 0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2;

    // Dedicated hot wallet for rate updates — NOT the owner key
    address constant RATE_UPDATER = 0x8ae7aF53C79fdce7b22B6BaB9868D85A25f27799;

    function run() external {
        require(RATE_UPDATER != address(0), "Set RATE_UPDATER before deploying");

        // Current rates from Coco FX API (as of 2026-03-27):
        //   crixtoRecharge (buy):  704.57 VES/USD — user mints VESC at this rate
        //   crixtoWithdraw (sell): 612.43 VES/USD — user burns VESC at this rate
        // buyRate > sellRate — the spread is the protocol margin.
        // Oracle will refresh these within 15 minutes of its first run post-deploy.
        uint256 initialBuyRate  = 704 * 1e18;
        uint256 initialSellRate = 612 * 1e18;

        vm.startBroadcast();

        VESCToken token = new VESCToken();

        // Deploy implementation (constructor disables initializers)
        VESCVault impl = new VESCVault();

        // Encode initialize() call
        bytes memory initData = abi.encodeCall(
            VESCVault.initialize,
            (USDC, address(token), initialBuyRate, initialSellRate)
        );

        // Deploy proxy — initialize() runs inside the constructor
        ERC1967Proxy proxy = new ERC1967Proxy(address(impl), initData);
        VESCVault vault = VESCVault(address(proxy));

        token.setVault(address(vault));
        token.renounceOwnership();
        vault.setRateUpdater(RATE_UPDATER);
        vault.setRescueToken(USDT, true);

        vm.stopBroadcast();
    }
}
