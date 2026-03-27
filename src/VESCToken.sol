// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

contract VESCToken is ERC20, Ownable {
    address public vault;

    error OnlyVault();
    error VaultAlreadySet();
    error ZeroAddress();

    modifier onlyVault() {
        if (msg.sender != vault) revert OnlyVault();
        _;
    }

    constructor() ERC20("VESC", "VESC") Ownable(msg.sender) {}

    /// @notice Set vault address (one-time, by owner)
    function setVault(address _vault) external onlyOwner {
        if (vault != address(0)) revert VaultAlreadySet();
        if (_vault == address(0)) revert ZeroAddress();
        vault = _vault;
    }

    function mint(address to, uint256 amount) external onlyVault {
        _mint(to, amount);
    }

    function burn(address from, uint256 amount) external onlyVault {
        _burn(from, amount);
    }
}
