// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Script} from "forge-std/Script.sol";
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

        // Initial rates — oracle will update these within 15 minutes of first run.
        // sellRate: VES per USD for mint (more VES per dollar — crixtoWithdraw)
        // buyRate:  VES per USD for burn (fewer VES per dollar — crixtoRecharge)
        // Set conservatively close to current market; buyRate must be < sellRate.
        uint256 initialSellRate = 612 * 1e18;  // ~612 VES/USD sell (update to current before deploying)
        uint256 initialBuyRate  = 600 * 1e18;  // ~600 VES/USD buy  (update to current before deploying)

        vm.startBroadcast();

        VESCToken token = new VESCToken();
        VESCVault vault = new VESCVault(USDC, address(token), initialSellRate, initialBuyRate);
        token.setVault(address(vault));
        token.renounceOwnership(); // vault is locked in; owner role is permanently inert
        vault.setRateUpdater(RATE_UPDATER);
        vault.setRescueToken(USDT, true);  // pre-approve USDT as emergency escape asset
        // NOTE: vault ownership stays with deployer initially.
        // Once volume warrants it, transfer to a Gnosis Safe multisig via:
        // vault.transferOwnership(<multisig>)

        vm.stopBroadcast();
    }
}
