// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/// @notice The token surface VESCVault needs — implemented by both VESCToken and WVESToken.
interface IVaultToken {
    function mint(address to, uint256 amount) external;
    function burn(address from, uint256 amount) external;
    function totalSupply() external view returns (uint256);
}
