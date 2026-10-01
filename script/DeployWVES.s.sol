// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {ERC1967Proxy} from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";
import {WVESToken} from "../src/WVESToken.sol";
import {VESCVault} from "../src/VESCVault.sol";

/// Deploys wVES ("Bolívar Venezolano") + its own VESCVault proxy, alongside the live VESC stack.
/// ~/.foundry/bin/forge script script/DeployWVES.s.sol --rpc-url https://mainnet.base.org \
///   --broadcast --ledger --sender 0x7f221e26628877249ace0c01b5715e3c2a4e30f9
contract DeployWVES is Script {
    address constant USDC         = 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913;
    address constant USDT         = 0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2;
    address constant RATE_UPDATER = 0x1fDFEB8CFB872ACfB410F980A4FdabD6a8405fe1;
    address constant VESC_VAULT   = 0x50F50cF026837aB49f337927d2B3269a7DEDbc60;

    function run() external returns (WVESToken token, VESCVault vault) {
        // Start from the live VESC rates so the oracle's 5%-per-update cap applies to both vaults alike.
        uint256 buyRate  = VESCVault(VESC_VAULT).buyRate();
        uint256 sellRate = VESCVault(VESC_VAULT).sellRate();

        vm.startBroadcast();
        address admin = msg.sender;

        token = WVESToken(address(new ERC1967Proxy(
            address(new WVESToken()),
            abi.encodeCall(WVESToken.initialize, (admin, unicode"Bolívar Venezolano", "wVES"))
        )));

        vault = VESCVault(address(new ERC1967Proxy(
            address(new VESCVault()),
            abi.encodeCall(VESCVault.initialize, (USDC, address(token), buyRate, sellRate))
        )));

        token.grantRole(token.MINTER_ROLE(), address(vault));
        vault.setRateUpdater(RATE_UPDATER);
        vault.setRescueToken(USDT, true);

        vm.stopBroadcast();

        console.log("wVES token proxy:", address(token));
        console.log("wVES vault proxy:", address(vault));
    }
}
