// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test, console} from "forge-std/Test.sol";
import {ERC1967Proxy} from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";
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
    // Real-world rates from Coco FX API (VES per USD):
    // buyRate > sellRate — the spread between them is the protocol margin.
    uint256 constant BUY_RATE  = 704 * 1e18;  // mint: user gets 704 VESC per USDC
    uint256 constant SELL_RATE = 612 * 1e18;  // burn: user gets USDC back at 612 VES/USD

    MockUSDC  usdc;
    VESCToken token;
    VESCVault vault;

    address alice = makeAddr("alice");
    address bob   = makeAddr("bob");

    function setUp() public {
        usdc  = new MockUSDC();
        token = new VESCToken();
        VESCVault impl = new VESCVault();
        vault = VESCVault(address(new ERC1967Proxy(
            address(impl),
            abi.encodeCall(VESCVault.initialize, (address(usdc), address(token), BUY_RATE, SELL_RATE))
        )));
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

    // Vault holds usdcIn from mint but burn at sellRate may need more — seed the shortfall
    function _seedShortfall(uint256 vescAmount, uint256 usdcAlreadyInVault) internal {
        uint256 grossUsdc = vescAmount * 1e6 / SELL_RATE;
        uint256 shortfall = grossUsdc > usdcAlreadyInVault ? grossUsdc - usdcAlreadyInVault : 0;
        if (shortfall > 0) _mintUSDC(address(vault), shortfall);
    }

    // ── Basic mint (uses buyRate) ────────────────────────────────────────────

    function test_Mint() public {
        uint256 usdcIn = 100e6;
        _mintUSDC(alice, usdcIn);
        _approveAndMint(alice, usdcIn);

        // 100 USDC * 704e18 / 1e6 = 70400e18 VESC
        assertEq(token.balanceOf(alice), 70_400e18);
        assertEq(usdc.balanceOf(address(vault)), usdcIn);
    }

    // ── Basic burn (uses sellRate) ───────────────────────────────────────────

    function test_Burn() public {
        uint256 usdcIn = 100e6;
        _mintUSDC(alice, usdcIn);
        _approveAndMint(alice, usdcIn);

        uint256 vescIn    = token.balanceOf(alice);
        _seedShortfall(vescIn, usdcIn);

        vm.prank(alice);
        vault.burn(vescIn, 0);

        uint256 grossUsdc  = vescIn * 1e6 / SELL_RATE;
        uint256 fee        = grossUsdc * 25 / 10_000;
        assertEq(usdc.balanceOf(alice), grossUsdc - fee);
        assertEq(token.balanceOf(alice), 0);
    }

    // ── Spread: burn always yields more USDC than mint cost ─────────────────

    function test_Spread_BurnYieldsMoreThanMintCost() public {
        uint256 usdcIn = 100e6;
        _mintUSDC(alice, usdcIn);
        _approveAndMint(alice, usdcIn);

        uint256 vescBal = token.balanceOf(alice);
        _seedShortfall(vescBal, usdcIn);

        vm.prank(alice);
        vault.burn(vescBal, 0);

        // buyRate(704) > sellRate(612): burning recovers more USDC (before fee)
        assertGt(usdc.balanceOf(alice), usdcIn);
    }

    // ── Fee calculation ──────────────────────────────────────────────────────

    function test_BurnFee() public {
        uint256 usdcIn = 100e6;
        _mintUSDC(alice, usdcIn);
        _approveAndMint(alice, usdcIn);

        uint256 vescBal   = token.balanceOf(alice);
        uint256 grossUsdc = vescBal * 1e6 / SELL_RATE;
        _seedShortfall(vescBal, usdcIn);

        uint256 fee = grossUsdc * 25 / 10_000;
        vm.prank(alice);
        vault.burn(vescBal, 0);

        assertEq(usdc.balanceOf(alice), grossUsdc - fee);
    }

    // ── setRates ─────────────────────────────────────────────────────────────

    function test_SetRates() public {
        uint256 newBuy  = BUY_RATE  * 105 / 100;
        uint256 newSell = SELL_RATE * 105 / 100;
        vm.warp(block.timestamp + vault.MIN_RATE_UPDATE_INTERVAL());

        vm.expectEmit(false, false, false, true);
        emit VESCVault.RatesUpdated(BUY_RATE, newBuy, SELL_RATE, newSell);

        vault.setRates(newBuy, newSell);
        assertEq(vault.buyRate(),  newBuy);
        assertEq(vault.sellRate(), newSell);
    }

    function test_SetRates_NonOwner_Reverts() public {
        vm.prank(alice);
        vm.expectRevert(VESCVault.NotRateUpdater.selector);
        vault.setRates(BUY_RATE * 105 / 100, SELL_RATE * 105 / 100);
    }

    function test_SetRates_BuyTooLarge_Reverts() public {
        // Drop both 90% (exceeds 20% cap); keep sell < buy to isolate the cap check
        vm.warp(block.timestamp + vault.MIN_RATE_UPDATE_INTERVAL());
        vm.expectRevert(VESCVault.RateChangeTooLarge.selector);
        vault.setRates(BUY_RATE / 10, SELL_RATE / 11);
    }

    function test_SetRates_SellTooLarge_Reverts() public {
        vm.warp(block.timestamp + vault.MIN_RATE_UPDATE_INTERVAL());
        vm.expectRevert(VESCVault.RateChangeTooLarge.selector);
        vault.setRates(BUY_RATE * 105 / 100, SELL_RATE / 10);
    }

    function test_SetRates_SellExceedsBuy_Reverts() public {
        vm.warp(block.timestamp + vault.MIN_RATE_UPDATE_INTERVAL());
        vm.expectRevert(VESCVault.SellRateExceedsBuyRate.selector);
        vault.setRates(SELL_RATE, BUY_RATE); // swapped: sell > buy
    }

    function test_SetRates_TooFrequent_Reverts() public {
        vm.expectRevert(VESCVault.RateUpdateTooFrequent.selector);
        vault.setRates(BUY_RATE * 105 / 100, SELL_RATE * 105 / 100);
    }

    function test_SetRates_ByRateUpdater() public {
        vault.setRateUpdater(alice);
        vm.warp(block.timestamp + vault.MIN_RATE_UPDATE_INTERVAL());
        vm.prank(alice);
        vault.setRates(BUY_RATE * 105 / 100, SELL_RATE * 105 / 100);
        assertEq(vault.buyRate(),  BUY_RATE  * 105 / 100);
        assertEq(vault.sellRate(), SELL_RATE * 105 / 100);
    }

    // ── Invariant checked on setRates ────────────────────────────────────────

    function test_SetRates_Decrease_WithInsufficientReserves_Reverts() public {
        uint256 usdcIn = 100e6;
        _mintUSDC(alice, usdcIn);
        _approveAndMint(alice, usdcIn);

        // Drop sellRate 19%: requiredReserves = totalSupply * 1e6 / newSellRate rises
        uint256 newSell = SELL_RATE * 81 / 100;
        uint256 newBuy  = BUY_RATE  * 81 / 100;
        vm.warp(block.timestamp + vault.MIN_RATE_UPDATE_INTERVAL());
        vm.expectRevert(VESCVault.InvariantViolation.selector);
        vault.setRates(newBuy, newSell);
    }

    // ── Slippage ─────────────────────────────────────────────────────────────

    function test_Mint_Slippage_Reverts() public {
        uint256 usdcIn = 100e6;
        _mintUSDC(alice, usdcIn);
        uint256 expectedVesc = usdcIn * BUY_RATE / 1e6;

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
        uint256 grossUsdc = vescBal * 1e6 / SELL_RATE;
        uint256 netUsdc   = grossUsdc - grossUsdc * 25 / 10_000;
        _seedShortfall(vescBal, usdcIn);

        vm.prank(alice);
        vm.expectRevert(VESCVault.SlippageExceeded.selector);
        vault.burn(vescBal, netUsdc + 1);
    }

    // ── collectFees ──────────────────────────────────────────────────────────

    function test_CollectFees() public {
        uint256 usdcIn = 1000e6;
        _mintUSDC(alice, usdcIn);
        _approveAndMint(alice, usdcIn);

        uint256 vescBal = token.balanceOf(alice);
        _seedShortfall(vescBal, usdcIn);

        vm.prank(alice);
        vault.burn(vescBal, 0);

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

        uint256 vescBal = token.balanceOf(alice);
        _seedShortfall(vescBal, usdcIn);
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
        VESCToken t    = new VESCToken();
        VESCVault impl = new VESCVault();
        vm.expectRevert(VESCVault.RateZero.selector);
        new ERC1967Proxy(
            address(impl),
            abi.encodeCall(VESCVault.initialize, (address(usdc), address(t), 0, 0))
        );
    }

    function test_SellExceedsBuy_Constructor_Reverts() public {
        VESCToken t    = new VESCToken();
        VESCVault impl = new VESCVault();
        vm.expectRevert(VESCVault.SellRateExceedsBuyRate.selector);
        new ERC1967Proxy(
            address(impl),
            abi.encodeCall(VESCVault.initialize, (address(usdc), address(t), SELL_RATE, BUY_RATE))
        );
    }

    // ── Fuzz: mint ───────────────────────────────────────────────────────────

    function testFuzz_Mint(uint256 usdcAmount) public {
        usdcAmount = bound(usdcAmount, 1, 1_000_000_000e6);
        _mintUSDC(alice, usdcAmount);
        _approveAndMint(alice, usdcAmount);

        assertEq(token.balanceOf(alice), usdcAmount * BUY_RATE / 1e6);
        assertEq(usdc.balanceOf(address(vault)), usdcAmount);
    }

    // ── Fuzz: burn ───────────────────────────────────────────────────────────

    function testFuzz_Burn(uint256 usdcAmount) public {
        usdcAmount = bound(usdcAmount, 1, 1_000_000_000e6);
        _mintUSDC(alice, usdcAmount);
        _approveAndMint(alice, usdcAmount);

        uint256 vescAmount = token.balanceOf(alice);
        _seedShortfall(vescAmount, usdcAmount);

        vm.prank(alice);
        vault.burn(vescAmount, 0);

        uint256 grossUsdc = vescAmount * 1e6 / SELL_RATE;
        uint256 fee       = grossUsdc * 25 / 10_000;
        assertEq(usdc.balanceOf(alice), grossUsdc - fee);
        assertEq(token.balanceOf(alice), 0);
    }
}
