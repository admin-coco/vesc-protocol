// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";
import {ERC1967Proxy} from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {ERC20Permit} from "@openzeppelin/contracts/token/ERC20/extensions/ERC20Permit.sol";
import {IAccessControl} from "@openzeppelin/contracts/access/IAccessControl.sol";
import {Initializable} from "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import {WVESToken} from "../src/WVESToken.sol";
import {VESCVault} from "../src/VESCVault.sol";

contract PermitUSDC is ERC20Permit {
    constructor() ERC20("USD Coin", "USDC") ERC20Permit("USD Coin") {}
    function decimals() public pure override returns (uint8) { return 6; }
    function mint(address to, uint256 amount) external { _mint(to, amount); }
}

contract WVESTokenV2 is WVESToken {
    function version() external pure returns (uint256) { return 2; }
}

contract WVESTest is Test {
    uint256 constant BUY_RATE  = 704 * 1e18;
    uint256 constant SELL_RATE = 612 * 1e18;
    bytes32 constant PERMIT_TYPEHASH =
        keccak256("Permit(address owner,address spender,uint256 value,uint256 nonce,uint256 deadline)");

    PermitUSDC usdc;
    WVESToken  token;
    VESCVault  vault;

    address admin = makeAddr("admin");
    uint256 alicePk = 0xA11CE;
    address alice;
    address bob = makeAddr("bob");

    function setUp() public {
        alice = vm.addr(alicePk);
        usdc  = new PermitUSDC();

        token = WVESToken(address(new ERC1967Proxy(
            address(new WVESToken()),
            abi.encodeCall(WVESToken.initialize, (admin, unicode"Bolívar Venezolano", "wVES"))
        )));
        vault = VESCVault(address(new ERC1967Proxy(
            address(new VESCVault()),
            abi.encodeCall(VESCVault.initialize, (address(usdc), address(token), BUY_RATE, SELL_RATE))
        )));

        bytes32 minterRole = token.MINTER_ROLE();
        vm.prank(admin);
        token.grantRole(minterRole, address(vault));
    }

    function _sign(uint256 pk, bytes32 domainSeparator, address owner, address spender, uint256 value, uint256 nonce, uint256 deadline)
        internal
        pure
        returns (uint8 v, bytes32 r, bytes32 s)
    {
        bytes32 structHash = keccak256(abi.encode(PERMIT_TYPEHASH, owner, spender, value, nonce, deadline));
        return vm.sign(pk, keccak256(abi.encodePacked("\x19\x01", domainSeparator, structHash)));
    }

    // ── Token metadata & roles ───────────────────────────────────────────────

    function test_metadata() public view {
        assertEq(token.name(), unicode"Bolívar Venezolano");
        assertEq(token.symbol(), "wVES");
        assertEq(token.decimals(), 18);
        (, string memory domainName, string memory domainVersion, uint256 chainId, address verifying,,) = token.eip712Domain();
        assertEq(domainName, unicode"Bolívar Venezolano");
        assertEq(domainVersion, "1");
        assertEq(chainId, block.chainid);
        assertEq(verifying, address(token));
    }

    function test_roles() public view {
        assertTrue(token.hasRole(token.DEFAULT_ADMIN_ROLE(), admin));
        assertTrue(token.hasRole(token.UPGRADER_ROLE(), admin));
        assertTrue(token.hasRole(token.MINTER_ROLE(), address(vault)));
        assertFalse(token.hasRole(token.MINTER_ROLE(), admin));
    }

    function test_onlyMinterCanMintOrBurn() public {
        bytes32 minterRole = token.MINTER_ROLE();
        vm.expectRevert(abi.encodeWithSelector(IAccessControl.AccessControlUnauthorizedAccount.selector, admin, minterRole));
        vm.prank(admin);
        token.mint(admin, 1);

        vm.expectRevert(abi.encodeWithSelector(IAccessControl.AccessControlUnauthorizedAccount.selector, bob, minterRole));
        vm.prank(bob);
        token.burn(bob, 0);
    }

    function test_cannotReinitialize() public {
        vm.expectRevert(Initializable.InvalidInitialization.selector);
        token.initialize(bob, "x", "x");
    }

    function test_implementationLocked() public {
        WVESToken impl = new WVESToken();
        vm.expectRevert(Initializable.InvalidInitialization.selector);
        impl.initialize(bob, "x", "x");
    }

    // ── Upgrades ─────────────────────────────────────────────────────────────

    function test_upgradeKeepsBalancesAndName() public {
        usdc.mint(bob, 100e6);
        vm.startPrank(bob);
        usdc.approve(address(vault), 100e6);
        vault.mint(100e6, 0);
        vm.stopPrank();
        uint256 bal = token.balanceOf(bob);

        address v2 = address(new WVESTokenV2());
        vm.prank(admin);
        token.upgradeToAndCall(v2, "");

        assertEq(WVESTokenV2(address(token)).version(), 2);
        assertEq(token.balanceOf(bob), bal);
        assertEq(token.name(), unicode"Bolívar Venezolano");
        assertTrue(token.hasRole(token.MINTER_ROLE(), address(vault)));
    }

    function test_onlyUpgraderCanUpgrade() public {
        address v2 = address(new WVESTokenV2());
        bytes32 upgraderRole = token.UPGRADER_ROLE();
        vm.expectRevert(abi.encodeWithSelector(IAccessControl.AccessControlUnauthorizedAccount.selector, bob, upgraderRole));
        vm.prank(bob);
        token.upgradeToAndCall(v2, "");
    }

    // ── Vault round trip ─────────────────────────────────────────────────────

    function test_mintBurnRoundTrip() public {
        usdc.mint(bob, 100e6);
        vm.startPrank(bob);
        usdc.approve(address(vault), 100e6);
        vault.mint(100e6, 0);
        assertEq(token.balanceOf(bob), 100e6 * SELL_RATE / 1e6);

        uint256 wves = token.balanceOf(bob);
        (uint256 expectedUsdc,) = vault.previewBurn(wves);
        vault.burn(wves, expectedUsdc);
        vm.stopPrank();

        assertEq(token.balanceOf(bob), 0);
        assertEq(token.totalSupply(), 0);
        assertEq(usdc.balanceOf(bob), expectedUsdc);
        assertGe(vault.usdcReserves(), vault.requiredReserves());
    }

    function testFuzz_mintBurnKeepsInvariant(uint256 usdcIn) public {
        usdcIn = bound(usdcIn, 1, 10_000_000e6);
        usdc.mint(bob, usdcIn);
        vm.startPrank(bob);
        usdc.approve(address(vault), usdcIn);
        vault.mint(usdcIn, 0);
        vault.burn(token.balanceOf(bob), 0);
        vm.stopPrank();
        assertGe(vault.usdcReserves(), vault.requiredReserves());
    }

    // ── mintWithPermit ───────────────────────────────────────────────────────

    function test_mintWithPermit() public {
        usdc.mint(alice, 50e6);
        uint256 deadline = block.timestamp + 1 hours;
        bytes32 ds = usdc.DOMAIN_SEPARATOR();
        (uint8 v, bytes32 r, bytes32 s) = _sign(alicePk, ds, alice, address(vault), 50e6, 0, deadline);

        uint256 expected = vault.previewMint(50e6);
        vm.prank(alice);
        vault.mintWithPermit(50e6, expected, deadline, v, r, s);

        assertEq(token.balanceOf(alice), expected);
        assertEq(usdc.balanceOf(address(vault)), 50e6);
        assertEq(usdc.nonces(alice), 1);
    }

    function test_mintWithPermit_survivesFrontRunPermit() public {
        usdc.mint(alice, 50e6);
        uint256 deadline = block.timestamp + 1 hours;
        bytes32 ds = usdc.DOMAIN_SEPARATOR();
        (uint8 v, bytes32 r, bytes32 s) = _sign(alicePk, ds, alice, address(vault), 50e6, 0, deadline);

        // Attacker submits the signature first; the mint must still go through
        vm.prank(bob);
        usdc.permit(alice, address(vault), 50e6, deadline, v, r, s);

        vm.prank(alice);
        vault.mintWithPermit(50e6, 0, deadline, v, r, s);
        assertEq(token.balanceOf(alice), vault.previewMint(50e6));
    }

    function test_mintWithPermit_badSigNoAllowanceReverts() public {
        usdc.mint(alice, 50e6);
        uint256 deadline = block.timestamp + 1 hours;
        bytes32 ds = usdc.DOMAIN_SEPARATOR();
        (uint8 v, bytes32 r, bytes32 s) = _sign(0xBAD, ds, alice, address(vault), 50e6, 0, deadline);

        vm.expectRevert();
        vm.prank(alice);
        vault.mintWithPermit(50e6, 0, deadline, v, r, s);
    }

    function test_mintWithPermit_respectsPause() public {
        vm.prank(vault.owner());
        vault.pause();
        vm.expectRevert();
        vm.prank(alice);
        vault.mintWithPermit(1e6, 0, block.timestamp, 0, bytes32(0), bytes32(0));
    }

    // ── wVES's own permit (EIP-2612, like wARS) ──────────────────────────────

    function test_tokenPermit() public {
        uint256 deadline = block.timestamp + 1 hours;
        bytes32 ds = token.DOMAIN_SEPARATOR();
        (uint8 v, bytes32 r, bytes32 s) = _sign(alicePk, ds, alice, bob, 123e18, 0, deadline);
        token.permit(alice, bob, 123e18, deadline, v, r, s);
        assertEq(token.allowance(alice, bob), 123e18);
    }
}
