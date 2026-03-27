// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {VESCToken} from "./VESCToken.sol";

contract VESCVault is Ownable, Pausable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    VESCToken public immutable vesc;
    IERC20    public immutable usdc;

    uint256 public sellRate;       // VES per USD used for mint, 18 decimals (more VES per dollar)
    uint256 public buyRate;        // VES per USD used for burn, 18 decimals (fewer VES per dollar)
    uint256 public constant FEE_BPS = 25;   // 0.25%
    uint256 public constant BPS     = 10_000;
    uint256 public constant MAX_RATE_CHANGE_BPS     = 2_000;       // 20% max per update
    uint256 public constant MAX_RATE_STALENESS       = 30 minutes;
    uint256 public constant MIN_RATE_UPDATE_INTERVAL = 10 minutes;

    // USDC has 6 decimals; used for scaling
    uint256 private constant USDC_SCALE = 1e6;

    address public rateUpdater;
    uint256 public lastRateUpdate;
    bool    public emergencyMode;

    mapping(address => bool) public rescueTokens;

    error RateZero();
    error UsdcAmountZero();
    error VescAmountZero();
    error InvariantViolation();
    error RateChangeTooLarge();
    error RateUpdateTooFrequent();
    error RateStale();
    error NotRateUpdater();
    error ZeroAddress();
    error SlippageExceeded();
    error NoFeesToCollect();
    error TokenNotApproved();
    error ZeroSupply();
    error NotEmergencyMode();
    error RescueTokenIsUsdc();
    error SwapRouterZero();
    error SwapFailed();
    error SwapProducedNoTokens();
    error SwapSlippageExceeded();
    error BuyRateExceedsSellRate();

    event RatesUpdated(uint256 oldSellRate, uint256 newSellRate, uint256 oldBuyRate, uint256 newBuyRate);
    event RateUpdaterSet(address indexed oldUpdater, address indexed newUpdater);
    event Minted(address indexed user, uint256 usdcIn, uint256 vescOut);
    event Burned(address indexed user, uint256 vescIn, uint256 usdcOut, uint256 fee);
    event FeesCollected(address indexed recipient, uint256 amount);
    event RescueTokenSet(address indexed token, bool approved);
    event EmergencyModeSet(bool enabled);
    event ReservesSwapped(address indexed rescueToken, uint256 usdcSpent, uint256 tokenReceived);
    event EmergencyRedeemed(address indexed user, address indexed token, uint256 vescIn, uint256 tokenOut);

    modifier onlyRateUpdater() {
        if (msg.sender != rateUpdater && msg.sender != owner()) revert NotRateUpdater();
        _;
    }

    constructor(address _usdc, address _vesc, uint256 initialSellRate, uint256 initialBuyRate) Ownable(msg.sender) {
        if (_usdc == address(0) || _vesc == address(0)) revert ZeroAddress();
        if (initialSellRate == 0 || initialBuyRate == 0) revert RateZero();
        if (initialBuyRate > initialSellRate) revert BuyRateExceedsSellRate();
        usdc = IERC20(_usdc);
        vesc = VESCToken(_vesc);
        sellRate = initialSellRate;
        buyRate  = initialBuyRate;
        lastRateUpdate = block.timestamp;
    }

    // ── Admin ────────────────────────────────────────────────────────────────

    function setRateUpdater(address _rateUpdater) external onlyOwner {
        emit RateUpdaterSet(rateUpdater, _rateUpdater);
        rateUpdater = _rateUpdater;
    }

    function collectFees(address recipient) external onlyOwner {
        if (recipient == address(0)) revert ZeroAddress();
        uint256 reserves = usdcReserves();
        uint256 required = requiredReserves();
        if (reserves <= required) revert NoFeesToCollect();
        uint256 surplus = reserves - required;
        emit FeesCollected(recipient, surplus);
        usdc.safeTransfer(recipient, surplus);
    }

    /// @notice Push both buy and sell rates on-chain atomically.
    /// @param newSellRate  VES per USD for mint (higher — more VES per dollar)
    /// @param newBuyRate   VES per USD for burn (lower — fewer VES per dollar)
    function setRates(uint256 newSellRate, uint256 newBuyRate) external onlyRateUpdater {
        if (newSellRate == 0 || newBuyRate == 0) revert RateZero();
        if (block.timestamp - lastRateUpdate < MIN_RATE_UPDATE_INTERVAL) revert RateUpdateTooFrequent();
        if (newBuyRate > newSellRate) revert BuyRateExceedsSellRate();

        uint256 oldSell = sellRate;
        uint256 oldBuy  = buyRate;

        uint256 sellDelta = newSellRate > oldSell ? newSellRate - oldSell : oldSell - newSellRate;
        if (sellDelta * BPS > oldSell * MAX_RATE_CHANGE_BPS) revert RateChangeTooLarge();

        uint256 buyDelta = newBuyRate > oldBuy ? newBuyRate - oldBuy : oldBuy - newBuyRate;
        if (buyDelta * BPS > oldBuy * MAX_RATE_CHANGE_BPS) revert RateChangeTooLarge();

        sellRate = newSellRate;
        buyRate  = newBuyRate;
        lastRateUpdate = block.timestamp;

        emit RatesUpdated(oldSell, newSellRate, oldBuy, newBuyRate);
        _checkInvariant();
    }

    function setRescueToken(address token, bool approved) external onlyOwner {
        if (token == address(0)) revert ZeroAddress();
        if (token == address(usdc)) revert RescueTokenIsUsdc();
        rescueTokens[token] = approved;
        emit RescueTokenSet(token, approved);
    }

    function setEmergencyMode(bool enabled) external onlyOwner {
        emergencyMode = enabled;
        emit EmergencyModeSet(enabled);
    }

    function swapReserves(
        address rescueToken,
        address router,
        bytes calldata swapData,
        uint256 minRescueOut
    ) external onlyOwner nonReentrant {
        if (!emergencyMode) revert NotEmergencyMode();
        if (!rescueTokens[rescueToken]) revert TokenNotApproved();
        if (router == address(0)) revert SwapRouterZero();

        uint256 usdcBalance = usdc.balanceOf(address(this));
        if (usdcBalance == 0) revert UsdcAmountZero();

        uint256 rescueBefore = IERC20(rescueToken).balanceOf(address(this));

        usdc.safeIncreaseAllowance(router, usdcBalance);
        (bool success,) = router.call(swapData);
        if (!success) revert SwapFailed();
        usdc.safeDecreaseAllowance(router, usdc.allowance(address(this), router));

        uint256 rescueReceived = IERC20(rescueToken).balanceOf(address(this)) - rescueBefore;
        if (rescueReceived == 0) revert SwapProducedNoTokens();
        if (rescueReceived < minRescueOut) revert SwapSlippageExceeded();

        emit ReservesSwapped(rescueToken, usdcBalance, rescueReceived);
    }

    function pause()   external onlyOwner { _pause(); }
    function unpause() external onlyOwner { _unpause(); }

    // ── User: Mint ───────────────────────────────────────────────────────────

    /// @notice Deposit USDC, receive VESC at current sell rate
    /// @param usdcAmount  Amount of USDC to deposit (6 decimals)
    /// @param minVescOut  Minimum VESC to receive
    function mint(uint256 usdcAmount, uint256 minVescOut) external nonReentrant whenNotPaused {
        if (usdcAmount == 0) revert UsdcAmountZero();
        if (block.timestamp - lastRateUpdate > MAX_RATE_STALENESS) revert RateStale();

        uint256 vescOut = usdcAmount * sellRate / USDC_SCALE;
        if (vescOut < minVescOut) revert SlippageExceeded();

        usdc.safeTransferFrom(msg.sender, address(this), usdcAmount);
        vesc.mint(msg.sender, vescOut);

        emit Minted(msg.sender, usdcAmount, vescOut);
    }

    // ── User: Burn ───────────────────────────────────────────────────────────

    /// @notice Burn VESC, receive USDC minus 0.25% fee, at current buy rate
    /// @param vescAmount  Amount of VESC to burn (18 decimals)
    /// @param minUsdcOut  Minimum USDC to receive
    function burn(uint256 vescAmount, uint256 minUsdcOut) external nonReentrant whenNotPaused {
        if (vescAmount == 0) revert VescAmountZero();
        if (block.timestamp - lastRateUpdate > MAX_RATE_STALENESS) revert RateStale();

        uint256 grossUsdc = vescAmount * USDC_SCALE / buyRate;
        uint256 fee       = grossUsdc * FEE_BPS / BPS;
        uint256 netUsdc   = grossUsdc - fee;
        if (netUsdc < minUsdcOut) revert SlippageExceeded();

        vesc.burn(msg.sender, vescAmount);
        usdc.safeTransfer(msg.sender, netUsdc);

        _checkInvariant();

        emit Burned(msg.sender, vescAmount, netUsdc, fee);
    }

    // ── Emergency Redemption ─────────────────────────────────────────────────

    function emergencyRedeem(address token, uint256 vescAmount) external nonReentrant {
        if (!emergencyMode) revert NotEmergencyMode();
        if (!rescueTokens[token]) revert TokenNotApproved();
        if (vescAmount == 0) revert VescAmountZero();
        uint256 totalSupply = vesc.totalSupply();
        if (totalSupply == 0) revert ZeroSupply();

        uint256 tokenBalance = IERC20(token).balanceOf(address(this));
        uint256 tokenOut = (vescAmount * tokenBalance) / totalSupply;

        vesc.burn(msg.sender, vescAmount);
        IERC20(token).safeTransfer(msg.sender, tokenOut);

        emit EmergencyRedeemed(msg.sender, token, vescAmount, tokenOut);
    }

    // ── View ─────────────────────────────────────────────────────────────────

    /// @notice Preview VESC out for a given USDC deposit (uses sell rate)
    function previewMint(uint256 usdcAmount) external view returns (uint256 vescOut) {
        vescOut = usdcAmount * sellRate / USDC_SCALE;
    }

    /// @notice Preview net USDC out for a given VESC burn (uses buy rate)
    function previewBurn(uint256 vescAmount) external view returns (uint256 netUsdc, uint256 fee) {
        uint256 grossUsdc = vescAmount * USDC_SCALE / buyRate;
        fee     = grossUsdc * FEE_BPS / BPS;
        netUsdc = grossUsdc - fee;
    }

    /// @notice USDC required to fully back current VESC supply at current buy rate
    function requiredReserves() public view returns (uint256) {
        return vesc.totalSupply() * USDC_SCALE / buyRate;
    }

    /// @notice Current USDC balance held by vault
    function usdcReserves() public view returns (uint256) {
        return usdc.balanceOf(address(this));
    }

    // ── Internal ─────────────────────────────────────────────────────────────

    function _checkInvariant() internal view {
        if (usdcReserves() < requiredReserves()) revert InvariantViolation();
    }
}
