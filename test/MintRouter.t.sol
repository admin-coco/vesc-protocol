// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";
import {ERC1967Proxy} from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";
import {VESCToken} from "../src/VESCToken.sol";
import {VESCVault} from "../src/VESCVault.sol";
import {MintRouter} from "../src/MintRouter.sol";

// Minimal ERC20 mock for USDC (6 decimals) — mirrors VESCVault.t.sol
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

contract MintRouterTest is Test {
    uint256 constant BUY_RATE  = 704 * 1e18;
    uint256 constant SELL_RATE = 612 * 1e18;

    MockUSDC   usdc;
    VESCToken  token;
    VESCVault  vault;
    MintRouter router;

    address alice    = makeAddr("alice");
    address bob      = makeAddr("bob");
    address fallback_ = makeAddr("fallback");

    bytes32 constant ORDER_ID = keccak256("order-1");

    function setUp() public {
        usdc  = new MockUSDC();
        token = new VESCToken();
        VESCVault impl = new VESCVault();
        vault = VESCVault(address(new ERC1967Proxy(
            address(impl),
            abi.encodeCall(VESCVault.initialize, (address(usdc), address(token), BUY_RATE, SELL_RATE))
        )));
        token.setVault(address(vault));
        router = new MintRouter(address(vault), address(usdc), address(token));
    }

    // ── Helpers ──────────────────────────────────────────────────────────────

    /// Simulate the DLN adapter: transfer USDC to the router, then invoke the hook.
    function _hook(uint256 usdcAmount, address beneficiary, uint256 minVescOut)
        internal
        returns (bool ok, bytes memory result)
    {
        usdc.mint(address(router), usdcAmount);
        (ok, result) = router.onERC20Received(
            ORDER_ID, address(usdc), usdcAmount, fallback_, abi.encode(beneficiary, minVescOut)
        );
    }

    // ── Hook: happy path ─────────────────────────────────────────────────────

    function test_Hook_MintsToBeneficiary() public {
        uint256 usdcIn = 100e6;
        (bool ok, bytes memory result) = _hook(usdcIn, alice, 0);

        assertTrue(ok);
        assertEq(abi.decode(result, (uint256)), 61_200e18);
        assertEq(token.balanceOf(alice), 61_200e18);
        assertEq(usdc.balanceOf(address(vault)), usdcIn);
        assertEq(usdc.balanceOf(address(router)), 0);
        assertEq(token.balanceOf(address(router)), 0);
    }

    function test_Hook_EmitsMintedFor() public {
        uint256 usdcIn = 100e6;
        usdc.mint(address(router), usdcIn);

        vm.expectEmit(true, true, false, true);
        emit MintRouter.MintedFor(alice, usdcIn, 61_200e18, ORDER_ID);

        router.onERC20Received(ORDER_ID, address(usdc), usdcIn, fallback_, abi.encode(alice, uint256(0)));
    }

    // ── Hook: failure paths refund to fallback, never revert ────────────────

    function test_Hook_StaleRate_RefundsFallback() public {
        vm.warp(block.timestamp + vault.MAX_RATE_STALENESS() + 1);

        (bool ok,) = _hook(100e6, alice, 0);

        assertFalse(ok);
        assertEq(usdc.balanceOf(fallback_), 100e6);
        assertEq(token.balanceOf(alice), 0);
        assertEq(usdc.balanceOf(address(router)), 0);
    }

    function test_Hook_SlippageExceeded_RefundsFallback() public {
        uint256 usdcIn = 100e6;
        uint256 tooHigh = usdcIn * SELL_RATE / 1e6 + 1;

        (bool ok,) = _hook(usdcIn, alice, tooHigh);

        assertFalse(ok);
        assertEq(usdc.balanceOf(fallback_), usdcIn);
        assertEq(token.balanceOf(alice), 0);
    }

    function test_Hook_PausedVault_RefundsFallback() public {
        vault.pause();

        (bool ok,) = _hook(100e6, alice, 0);

        assertFalse(ok);
        assertEq(usdc.balanceOf(fallback_), 100e6);
    }

    function test_Hook_EmergencyMode_RefundsFallback() public {
        vault.setEmergencyMode(true);

        (bool ok,) = _hook(100e6, alice, 0);

        assertFalse(ok);
        assertEq(usdc.balanceOf(fallback_), 100e6);
    }

    function test_Hook_WrongToken_RefundsFallback() public {
        MockUSDC other = new MockUSDC();
        other.mint(address(router), 100e6);

        (bool ok,) = router.onERC20Received(
            ORDER_ID, address(other), 100e6, fallback_, abi.encode(alice, uint256(0))
        );

        assertFalse(ok);
        assertEq(other.balanceOf(fallback_), 100e6);
    }

    function test_Hook_MalformedPayload_RefundsFallback() public {
        usdc.mint(address(router), 100e6);

        (bool ok,) = router.onERC20Received(ORDER_ID, address(usdc), 100e6, fallback_, hex"deadbeef");

        assertFalse(ok);
        assertEq(usdc.balanceOf(fallback_), 100e6);
    }

    function test_Hook_DirtyAddressWord_RefundsFallback() public {
        usdc.mint(address(router), 100e6);
        // Top bits set in the address word — must refund, not revert or mint
        bytes memory payload = abi.encode(uint256(type(uint256).max), uint256(0));

        (bool ok,) = router.onERC20Received(ORDER_ID, address(usdc), 100e6, fallback_, payload);

        assertFalse(ok);
        assertEq(usdc.balanceOf(fallback_), 100e6);
    }

    function test_Hook_ZeroBeneficiary_RefundsFallback() public {
        usdc.mint(address(router), 100e6);

        (bool ok,) = router.onERC20Received(
            ORDER_ID, address(usdc), 100e6, fallback_, abi.encode(address(0), uint256(0))
        );

        assertFalse(ok);
        assertEq(usdc.balanceOf(fallback_), 100e6);
    }

    function test_Hook_EmitsHookRefunded() public {
        vault.pause();
        usdc.mint(address(router), 100e6);

        vm.expectEmit(true, true, false, true);
        emit MintRouter.HookRefunded(fallback_, address(usdc), 100e6, ORDER_ID);

        router.onERC20Received(ORDER_ID, address(usdc), 100e6, fallback_, abi.encode(alice, uint256(0)));
    }

    // ── onEtherReceived: forward to fallback ─────────────────────────────────

    function test_EtherReceived_ForwardsToFallback() public {
        vm.deal(alice, 1 ether);
        vm.prank(alice);
        (bool ok,) = router.onEtherReceived{value: 1 ether}(ORDER_ID, fallback_, "");

        assertFalse(ok);
        assertEq(fallback_.balance, 1 ether);
        assertEq(address(router).balance, 0);
    }

    // ── mintFor: direct path ─────────────────────────────────────────────────

    function test_MintFor() public {
        uint256 usdcIn = 100e6;
        usdc.mint(alice, usdcIn);

        vm.startPrank(alice);
        usdc.approve(address(router), usdcIn);
        uint256 vescOut = router.mintFor(bob, usdcIn, 0);
        vm.stopPrank();

        assertEq(vescOut, 61_200e18);
        assertEq(token.balanceOf(bob), 61_200e18);
        assertEq(usdc.balanceOf(address(vault)), usdcIn);
        assertEq(token.balanceOf(address(router)), 0);
    }

    function test_MintFor_Slippage_Reverts() public {
        uint256 usdcIn = 100e6;
        usdc.mint(alice, usdcIn);
        uint256 tooHigh = usdcIn * SELL_RATE / 1e6 + 1;

        vm.startPrank(alice);
        usdc.approve(address(router), usdcIn);
        vm.expectRevert(VESCVault.SlippageExceeded.selector);
        router.mintFor(bob, usdcIn, tooHigh);
        vm.stopPrank();
    }

    function test_MintFor_ZeroBeneficiary_Reverts() public {
        vm.prank(alice);
        vm.expectRevert(MintRouter.ZeroBeneficiary.selector);
        router.mintFor(address(0), 100e6, 0);
    }

    function test_MintFor_ZeroAmount_Reverts() public {
        vm.prank(alice);
        vm.expectRevert(MintRouter.UsdcAmountZero.selector);
        router.mintFor(bob, 0, 0);
    }

    // ── Constructor guards ───────────────────────────────────────────────────

    function test_Constructor_ZeroAddress_Reverts() public {
        vm.expectRevert(MintRouter.ZeroAddress.selector);
        new MintRouter(address(0), address(usdc), address(token));
        vm.expectRevert(MintRouter.ZeroAddress.selector);
        new MintRouter(address(vault), address(0), address(token));
        vm.expectRevert(MintRouter.ZeroAddress.selector);
        new MintRouter(address(vault), address(usdc), address(0));
    }

    // ── Fuzz ─────────────────────────────────────────────────────────────────

    function testFuzz_Hook(uint256 usdcAmount) public {
        usdcAmount = bound(usdcAmount, 1, 1_000_000_000e6);

        (bool ok,) = _hook(usdcAmount, alice, 0);

        assertTrue(ok);
        assertEq(token.balanceOf(alice), usdcAmount * SELL_RATE / 1e6);
        assertEq(usdc.balanceOf(address(vault)), usdcAmount);
        assertEq(usdc.balanceOf(address(router)), 0);
    }

    function testFuzz_MintFor(uint256 usdcAmount) public {
        usdcAmount = bound(usdcAmount, 1, 1_000_000_000e6);
        usdc.mint(alice, usdcAmount);

        vm.startPrank(alice);
        usdc.approve(address(router), usdcAmount);
        router.mintFor(bob, usdcAmount, 0);
        vm.stopPrank();

        assertEq(token.balanceOf(bob), usdcAmount * SELL_RATE / 1e6);
    }
}
