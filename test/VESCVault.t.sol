// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test, console} from "forge-std/Test.sol";
import {VESCToken} from "../src/VESCToken.sol";
import {VESCVault} from "../src/VESCVault.sol";

// Minimal ERC20 mock for USDC (6 decimals)
contract MockUSDC {
    string public name     = "USD Coin";
    string public symbol   = "USDC";
    uint8  public decimals = 6;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
        emit Transfer(address(0), to, amount);
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        require(balanceOf[msg.sender] >= amount, "insufficient");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        emit Transfer(msg.sender, to, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        require(balanceOf[from] >= amount, "insufficient");
        require(allowance[from][msg.sender] >= amount, "allowance");
        allowance[from][msg.sender] -= amount;
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        emit Transfer(from, to, amount);
        return true;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }
}

contract VESCVaultTest is Test {
    // Sell rate: 410 VES per USD (mint — user gets more VESC)
    // Buy  rate: 400 VES per USD (burn — user gets fewer USDC back)
    uint256 constant SELL_RATE = 410 * 1e18;
    uint256 constant BUY_RATE  = 400 * 1e18;

    MockUSDC  usdc;
    VESCToken token;
    VESCVault vault;

    address alice = makeAddr("alice");
    address bob   = makeAddr("bob");

    function setUp() public {
        usdc  = new MockUSDC();
        token = new VESCToken();
        vault = new VESCVault(address(usdc), address(token), SELL_RATE, BUY_RATE);
        token.setVault(address(vault));
    }

    // ── Helpers ──────────────────────────────────────────────────────────────

    function _mintUSDC(address to, uint256 amount) internal {
        usdc.mint(to, amount);
    }

    function _approveAndMint(address user, uint256 usdcAmount) internal {
        vm.startPrank(user);
        usdc.approve(address(vault), usdcAmount);
        vault.mint(usdcAmount, 0);
        vm.stopPrank();
    }

    // ── Basic mint (uses sellRate) ───────────────────────────────────────────

    function test_Mint() public {
        uint256 usdcIn = 100e6; // 100 USDC
        _mintUSDC(alice, usdcIn);
        _approveAndMint(alice, usdcIn);

        // 100 USDC * 410e18 / 1e6 = 41000e18 VESC
        assertEq(token.balanceOf(alice), 41_000e18);
        assertEq(usdc.balanceOf(address(vault)), usdcIn);
    }

    // ── Basic burn (uses buyRate) ────────────────────────────────────────────

    function test_Burn() public {
        uint256 usdcIn = 100e6;
        _mintUSDC(alice, usdcIn);
        _approveAndMint(alice, usdcIn);

        uint256 vescIn = token.balanceOf(alice); // 41000e18

        // Burn pays out at buyRate (400), but vault only holds 100 USDC from mint.
        // grossUsdc = 41000e18 * 1e6 / 400e18 = 102.5 USDC — seed the shortfall.
        uint256 grossUsdc = vescIn * 1e6 / BUY_RATE;
        uint256 shortfall = grossUsdc > usdcIn ? grossUsdc - usdcIn : 0;
        if (shortfall > 0) _mintUSDC(address(vault), shortfall);

        vm.startPrank(alice);
        vault.burn(vescIn, 0);
        vm.stopPrank();

        uint256 fee         = grossUsdc * 25 / 10_000;
        uint256 expectedNet = grossUsdc - fee;
        assertEq(usdc.balanceOf(alice), expectedNet);
        assertEq(token.balanceOf(alice), 0);
    }

    // ── Buy/sell spread: burn yields more USDC than mint cost ────────────────

    function test_Spread_BurnYieldsMoreThanMintCost() public {
        uint256 usdcIn = 100e6;
        _mintUSDC(alice, usdcIn);
        _approveAndMint(alice, usdcIn);

        uint256 vescBal   = token.balanceOf(alice);
        uint256 grossUsdc = vescBal * 1e6 / BUY_RATE;
        uint256 shortfall = grossUsdc > usdcIn ? grossUsdc - usdcIn : 0;
        if (shortfall > 0) _mintUSDC(address(vault), shortfall);

        vm.prank(alice);
        vault.burn(vescBal, 0);

        // buyRate < sellRate: burning recovers more USDC (before fee) than deposited.
        // Net after 0.25% fee should still exceed original deposit.
        assertGt(usdc.balanceOf(alice), usdcIn);
    }

    // ── Fee calculation ──────────────────────────────────────────────────────

    function test_BurnFee() public {
        uint256 usdcIn = 100e6;
        _mintUSDC(alice, usdcIn);
        _approveAndMint(alice, usdcIn);

        uint256 vescBal   = token.balanceOf(alice);
        uint256 grossUsdc = vescBal * 1e6 / BUY_RATE;
        uint256 shortfall = grossUsdc > usdcIn ? grossUsdc - usdcIn : 0;
        if (shortfall > 0) _mintUSDC(address(vault), shortfall);

        uint256 fee = grossUsdc * 25 / 10_000;

        vm.prank(alice);
        vault.burn(vescBal, 0);

        assertEq(usdc.balanceOf(alice), grossUsdc - fee);
    }

    // ── setRates ─────────────────────────────────────────────────────────────

    function test_SetRates() public {
        uint256 newSell = SELL_RATE * 105 / 100;
        uint256 newBuy  = BUY_RATE  * 105 / 100;
        vm.warp(block.timestamp + vault.MIN_RATE_UPDATE_INTERVAL());

        vm.expectEmit(false, false, false, true);
        emit VESCVault.RatesUpdated(SELL_RATE, newSell, BUY_RATE, newBuy);

        vault.setRates(newSell, newBuy);
        assertEq(vault.sellRate(), newSell);
        assertEq(vault.buyRate(),  newBuy);
    }

    function test_SetRates_NonOwner_Reverts() public {
        vm.prank(alice);
        vm.expectRevert(VESCVault.NotRateUpdater.selector);
        vault.setRates(SELL_RATE * 105 / 100, BUY_RATE * 105 / 100);
    }

    function test_SetRates_SellTooLarge_Reverts() public {
        // Drop both rates by 90% (exceeds 20% cap); keep buy < sell to isolate the cap check
        vm.warp(block.timestamp + vault.MIN_RATE_UPDATE_INTERVAL());
        vm.expectRevert(VESCVault.RateChangeTooLarge.selector);
        vault.setRates(SELL_RATE / 10, BUY_RATE / 11);
    }

    function test_SetRates_BuyTooLarge_Reverts() public {
        vm.warp(block.timestamp + vault.MIN_RATE_UPDATE_INTERVAL());
        vm.expectRevert(VESCVault.RateChangeTooLarge.selector);
        vault.setRates(SELL_RATE * 105 / 100, BUY_RATE / 10);
    }

    function test_SetRates_BuyExceedsSell_Reverts() public {
        vm.warp(block.timestamp + vault.MIN_RATE_UPDATE_INTERVAL());
        vm.expectRevert(VESCVault.BuyRateExceedsSellRate.selector);
        vault.setRates(BUY_RATE, SELL_RATE); // swapped: buy > sell
    }

    function test_SetRates_TooFrequent_Reverts() public {
        vm.expectRevert(VESCVault.RateUpdateTooFrequent.selector);
        vault.setRates(SELL_RATE * 105 / 100, BUY_RATE * 105 / 100);
    }

    function test_SetRates_ByRateUpdater() public {
        vault.setRateUpdater(alice);
        vm.warp(block.timestamp + vault.MIN_RATE_UPDATE_INTERVAL());
        vm.prank(alice);
        vault.setRates(SELL_RATE * 105 / 100, BUY_RATE * 105 / 100);
        assertEq(vault.sellRate(), SELL_RATE * 105 / 100);
        assertEq(vault.buyRate(),  BUY_RATE  * 105 / 100);
    }

    // ── Invariant checked on setRates ────────────────────────────────────────

    function test_SetRates_Decrease_WithInsufficientReserves_Reverts() public {
        uint256 usdcIn = 100e6;
        _mintUSDC(alice, usdcIn);
        _approveAndMint(alice, usdcIn);

        // Drop buyRate by 19%: requiredReserves = totalSupply * 1e6 / newBuyRate rises
        uint256 newBuy  = BUY_RATE  * 81 / 100;
        uint256 newSell = SELL_RATE * 81 / 100;
        vm.warp(block.timestamp + vault.MIN_RATE_UPDATE_INTERVAL());
        vm.expectRevert(VESCVault.InvariantViolation.selector);
        vault.setRates(newSell, newBuy);
    }

    // ── Slippage ─────────────────────────────────────────────────────────────

    function test_Mint_Slippage_Reverts() public {
        uint256 usdcIn = 100e6;
        _mintUSDC(alice, usdcIn);
        uint256 expectedVesc = usdcIn * SELL_RATE / 1e6;

        vm.startPrank(alice);
        usdc.approve(address(vault), usdcIn);
        vm.expectRevert(VESCVault.SlippageExceeded.selector);
        vault.mint(usdcIn, expectedVesc + 1);
        vm.stopPrank();
    }

    function test_Burn_Slippage_Reverts() public {
        uint256 usdcIn = 100e6;
        _mintUSDC(alice, usdcIn);
        _approveAndMint(alice, usdcIn);

        uint256 vescBal   = token.balanceOf(alice);
        uint256 grossUsdc = vescBal * 1e6 / BUY_RATE;
        uint256 netUsdc   = grossUsdc - grossUsdc * 25 / 10_000;

        vm.prank(alice);
        vm.expectRevert(VESCVault.SlippageExceeded.selector);
        vault.burn(vescBal, netUsdc + 1);
    }

    // ── collectFees ──────────────────────────────────────────────────────────

    function test_CollectFees() public {
        uint256 usdcIn = 1000e6;
        _mintUSDC(alice, usdcIn);
        _approveAndMint(alice, usdcIn);

        uint256 vescBal   = token.balanceOf(alice);
        uint256 grossUsdc = vescBal * 1e6 / BUY_RATE;
        uint256 shortfall = grossUsdc > usdcIn ? grossUsdc - usdcIn : 0;
        if (shortfall > 0) _mintUSDC(address(vault), shortfall);

        vm.prank(alice);
        vault.burn(vescBal, 0);

        // After full burn: totalSupply = 0, requiredReserves = 0, all USDC is surplus
        uint256 bobBefore = usdc.balanceOf(bob);
        vault.collectFees(bob);
        assertGt(usdc.balanceOf(bob) - bobBefore, 0);
        assertEq(vault.usdcReserves(), 0);
    }

    function test_CollectFees_NonOwner_Reverts() public {
        vm.prank(alice);
        vm.expectRevert();
        vault.collectFees(alice);
    }

    function test_CollectFees_NoSurplus_Reverts() public {
        vm.expectRevert(VESCVault.NoFeesToCollect.selector);
        vault.collectFees(bob);
    }

    // ── Pause ────────────────────────────────────────────────────────────────

    function test_Pause_Mint_Reverts() public {
        vault.pause();
        _mintUSDC(alice, 100e6);

        vm.startPrank(alice);
        usdc.approve(address(vault), 100e6);
        vm.expectRevert();
        vault.mint(100e6, 0);
        vm.stopPrank();
    }

    function test_Pause_Burn_Reverts() public {
        uint256 usdcIn = 100e6;
        _mintUSDC(alice, usdcIn);
        _approveAndMint(alice, usdcIn);

        // Seed vault so burn would succeed if not paused
        uint256 vescBal   = token.balanceOf(alice);
        uint256 grossUsdc = vescBal * 1e6 / BUY_RATE;
        uint256 shortfall = grossUsdc > usdcIn ? grossUsdc - usdcIn : 0;
        if (shortfall > 0) _mintUSDC(address(vault), shortfall);

        vault.pause();

        vm.prank(alice);
        vm.expectRevert();
        vault.burn(vescBal, 0);
    }

    // ── Zero-amount guards ───────────────────────────────────────────────────

    function test_MintZero_Reverts() public {
        vm.prank(alice);
        vm.expectRevert(VESCVault.UsdcAmountZero.selector);
        vault.mint(0, 0);
    }

    function test_BurnZero_Reverts() public {
        vm.prank(alice);
        vm.expectRevert(VESCVault.VescAmountZero.selector);
        vault.burn(0, 0);
    }

    // ── Constructor guards ───────────────────────────────────────────────────

    function test_RateZero_Reverts() public {
        VESCToken t = new VESCToken();
        vm.expectRevert(VESCVault.RateZero.selector);
        new VESCVault(address(usdc), address(t), 0, 0);
    }

    function test_BuyExceedsSell_Constructor_Reverts() public {
        VESCToken t = new VESCToken();
        vm.expectRevert(VESCVault.BuyRateExceedsSellRate.selector);
        new VESCVault(address(usdc), address(t), BUY_RATE, SELL_RATE);
    }

    // ── Fuzz: mint ───────────────────────────────────────────────────────────

    function testFuzz_Mint(uint256 usdcAmount) public {
        usdcAmount = bound(usdcAmount, 1, 1_000_000_000e6);
        _mintUSDC(alice, usdcAmount);
        _approveAndMint(alice, usdcAmount);

        assertEq(token.balanceOf(alice), usdcAmount * SELL_RATE / 1e6);
        assertEq(usdc.balanceOf(address(vault)), usdcAmount);
    }

    // ── Fuzz: burn ───────────────────────────────────────────────────────────

    function testFuzz_Burn(uint256 usdcAmount) public {
        usdcAmount = bound(usdcAmount, 1, 1_000_000_000e6);
        _mintUSDC(alice, usdcAmount);
        _approveAndMint(alice, usdcAmount);

        uint256 vescAmount = token.balanceOf(alice);
        uint256 grossUsdc  = vescAmount * 1e6 / BUY_RATE;
        uint256 shortfall  = grossUsdc > usdcAmount ? grossUsdc - usdcAmount : 0;
        if (shortfall > 0) _mintUSDC(address(vault), shortfall);

        vm.prank(alice);
        vault.burn(vescAmount, 0);

        uint256 fee = grossUsdc * 25 / 10_000;
        assertEq(usdc.balanceOf(alice), grossUsdc - fee);
        assertEq(token.balanceOf(alice), 0);
    }
}
