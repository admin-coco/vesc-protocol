// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {IERC20}    from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

interface IVESCVault {
    function mint(uint256 usdcAmount, uint256 minVescOut) external;
}

/// @notice deBridge DLN hook target interface. The DlnExternalCallAdapter transfers
///         the bridged tokens to the target first, then invokes one of these callbacks.
interface IExternalCallExecutor {
    function onEtherReceived(
        bytes32 _orderId,
        address _fallbackAddress,
        bytes memory _payload
    ) external payable returns (bool callSucceeded, bytes memory callResult);

    function onERC20Received(
        bytes32 _orderId,
        address _token,
        uint256 _transferredAmount,
        address _fallbackAddress,
        bytes memory _payload
    ) external returns (bool callSucceeded, bytes memory callResult);
}

/// @title MintRouter
/// @notice Stateless, unowned pass-through that mints VESC to a beneficiary in the same
///         transaction USDC arrives on Base. Designed as a deBridge DLN hook target
///         (USDT/USDC on any source chain → USDC Base → VESC, one user signature), but
///         permissionless: anyone holding USDC can also call mintFor directly.
/// @dev    Holds no funds between transactions and has no owner, roles, or pause —
///         pausing, rate staleness, and slippage are all enforced by the vault.
///         The hook path never reverts: any failure refunds the bridged tokens to the
///         user's fallback address so funds are never stranded here.
contract MintRouter is IExternalCallExecutor, ReentrancyGuard {
    using SafeERC20 for IERC20;

    IVESCVault public immutable vault;
    IERC20     public immutable usdc;
    IERC20     public immutable vesc;

    error ZeroAddress();
    error ZeroBeneficiary();
    error UsdcAmountZero();

    event MintedFor(address indexed beneficiary, uint256 usdcIn, uint256 vescOut, bytes32 indexed orderId);
    event HookRefunded(address indexed fallbackAddress, address token, uint256 amount, bytes32 indexed orderId);

    constructor(address _vault, address _usdc, address _vesc) {
        if (_vault == address(0) || _usdc == address(0) || _vesc == address(0)) revert ZeroAddress();
        vault = IVESCVault(_vault);
        usdc  = IERC20(_usdc);
        vesc  = IERC20(_vesc);
        // Router never holds USDC between transactions, so a standing allowance to the
        // vault only ever covers the amount in flight within a single tx.
        IERC20(_usdc).forceApprove(_vault, type(uint256).max);
    }

    // ── Direct path ──────────────────────────────────────────────────────────

    /// @notice Pull USDC from the caller, mint VESC at the current sell rate, deliver to beneficiary.
    /// @dev Reverts on any failure (vault paused, stale rate, slippage) — the caller initiated this.
    function mintFor(address beneficiary, uint256 usdcAmount, uint256 minVescOut)
        external
        nonReentrant
        returns (uint256 vescOut)
    {
        if (beneficiary == address(0)) revert ZeroBeneficiary();
        if (usdcAmount == 0) revert UsdcAmountZero();

        usdc.safeTransferFrom(msg.sender, address(this), usdcAmount);

        uint256 before = vesc.balanceOf(address(this));
        vault.mint(usdcAmount, minVescOut);
        vescOut = vesc.balanceOf(address(this)) - before;

        vesc.safeTransfer(beneficiary, vescOut);
        emit MintedFor(beneficiary, usdcAmount, vescOut, bytes32(0));
    }

    // ── deBridge hook path ───────────────────────────────────────────────────

    /// @notice Called by the DLN adapter after it transfers the bridged USDC here.
    ///         Payload: abi.encode(address beneficiary, uint256 minVescOut).
    /// @dev Never reverts: on any failure the tokens are forwarded to the fallback
    ///      address (the user's own wallet) and (false, "") is returned, so an
    ///      optional-success hook degrades to plain USDC delivery.
    function onERC20Received(
        bytes32 _orderId,
        address _token,
        uint256 _transferredAmount,
        address _fallbackAddress,
        bytes memory _payload
    ) external nonReentrant returns (bool callSucceeded, bytes memory callResult) {
        (address beneficiary, uint256 minVescOut, bool ok) = _decodePayload(_payload);

        if (!ok || _token != address(usdc) || _transferredAmount == 0) {
            _refund(_token, _transferredAmount, _fallbackAddress, _orderId);
            return (false, "");
        }

        uint256 before = vesc.balanceOf(address(this));
        try vault.mint(_transferredAmount, minVescOut) {
            uint256 vescOut = vesc.balanceOf(address(this)) - before;
            vesc.safeTransfer(beneficiary, vescOut);
            emit MintedFor(beneficiary, _transferredAmount, vescOut, _orderId);
            return (true, abi.encode(vescOut));
        } catch {
            _refund(_token, _transferredAmount, _fallbackAddress, _orderId);
            return (false, "");
        }
    }

    /// @notice Orders always buy USDC, never native currency; forward any ether to the fallback.
    function onEtherReceived(bytes32 _orderId, address _fallbackAddress, bytes memory)
        external
        payable
        returns (bool callSucceeded, bytes memory callResult)
    {
        uint256 amount = address(this).balance;
        if (amount > 0 && _fallbackAddress != address(0)) {
            (bool sent,) = _fallbackAddress.call{value: amount}("");
            if (sent) emit HookRefunded(_fallbackAddress, address(0), amount, _orderId);
        }
        return (false, "");
    }

    // ── Internal ─────────────────────────────────────────────────────────────

    /// @dev Decode abi.encode(address, uint256) without ever reverting on malformed input.
    function _decodePayload(bytes memory p)
        private
        pure
        returns (address beneficiary, uint256 minVescOut, bool ok)
    {
        if (p.length != 64) return (address(0), 0, false);
        uint256 word0;
        uint256 word1;
        assembly {
            word0 := mload(add(p, 32))
            word1 := mload(add(p, 64))
        }
        if (word0 > type(uint160).max || word0 == 0) return (address(0), 0, false);
        return (address(uint160(word0)), word1, true);
    }

    function _refund(address token, uint256 amount, address fallbackAddress, bytes32 orderId) private {
        if (amount == 0 || fallbackAddress == address(0)) return;
        IERC20(token).safeTransfer(fallbackAddress, amount);
        emit HookRefunded(fallbackAddress, token, amount, orderId);
    }
}
