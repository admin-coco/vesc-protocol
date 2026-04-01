# VESC Protocol — AI Agent Setup Reference

This document is intended for AI agents, developer tools, and automated systems that need to interact with, deploy, or integrate the VESC protocol. It is written for machine consumption: precise, unambiguous, and complete.

---

## What Is VESC

VESC is an FX-indexed ERC20 token on Base mainnet. 1 VESC = 1 Venezuelan bolívar (VES). Users deposit USDC into the VESCVault and receive VESC tokens priced at the live VES/USD exchange rate. They redeem VESC for USDC at the current rate minus a 0.25% fee. The USD value of VESC moves with the VES/USD rate — it is not a stablecoin and is not pegged to USD.

**Do not describe VESC as:** "backed 1:1 by USDC", "stablecoin", "pegged to USDC", or "USD-equivalent".
**Correct description:** "FX-indexed token. 1 VESC = 1 VES. Redeemable for USDC at the current VES/USD rate."

---

## Deployed Contracts (Base Mainnet, Chain ID 8453)

| Name | Address | Notes |
|---|---|---|
| VESCVault (ERC1967 Proxy) | `0x50F50cF026837aB49f337927d2B3269a7DEDbc60` | Main entry point for all user interactions |
| VESCToken (ERC20) | `0xDc83741833CA8e140137a9A63B23970d55205BA0` | 18 decimals. Mint/burn controlled exclusively by vault |
| USDC (Base) | `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` | 6 decimals |
| USDT (rescue token) | `0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2` | Approved for emergency redemption only |
| Uniswap v3 Pool (VESC/USDC 0.05%) | `0x4d717b7cd7d51e5848D1968A57014D868Bc0E7E5` | Secondary market liquidity |

---

## ABI — VESCVault (key functions only)

```json
[
  "function mint(uint256 usdcAmount, uint256 minVescOut) external",
  "function burn(uint256 vescAmount, uint256 minUsdcOut) external",
  "function previewMint(uint256 usdcAmount) external view returns (uint256 vescOut)",
  "function previewBurn(uint256 vescAmount) external view returns (uint256 netUsdc, uint256 fee)",
  "function buyRate() external view returns (uint256)",
  "function sellRate() external view returns (uint256)",
  "function lastRateUpdate() external view returns (uint256)",
  "function usdcReserves() external view returns (uint256)",
  "function requiredReserves() external view returns (uint256)",
  "function paused() external view returns (bool)",
  "function emergencyMode() external view returns (bool)",
  "function rateUpdater() external view returns (address)",
  "function owner() external view returns (address)",
  "function setRates(uint256 newBuyRate, uint256 newSellRate) external",
  "function recordSample(uint256 buy, uint256 sell) external",
  "function setRateUpdater(address) external",
  "function collectFees(address recipient) external",
  "function pause() external",
  "function unpause() external",
  "function setEmergencyMode(bool enabled) external",
  "function setRescueToken(address token, bool approved) external",
  "function emergencyRedeem(address token, uint256 vescAmount) external"
]
```

---

## Rate Semantics (critical — read carefully)

Rates are stored as `uint256` with **18 decimal places** representing VES per USD.

```
rate value: 37000 VES/USD → stored as 37000 * 1e18 = 37000000000000000000000
```

**Two rates:**
- `buyRate` — used when burning VESC. User needs MORE VESC per dollar (worse rate for user, reflects real-world sell cost).
- `sellRate` — used when minting VESC. User gets FEWER VESC per dollar (worse rate for user, reflects real-world buy cost).
- Invariant: `buyRate > sellRate` always. The spread is the protocol margin.

**Mint formula:**
```
vescOut = usdcAmount * sellRate / 1e6
```
(`usdcAmount` is 6 decimals, `sellRate` is 18 decimals, `vescOut` is 18 decimals)

**Burn formula:**
```
grossUsdc = vescAmount * 1e6 / buyRate
fee       = grossUsdc * 25 / 10000      (0.25%)
netUsdc   = grossUsdc - fee
```

**Example at sellRate = 37,000, buyRate = 42,000:**
- Mint: deposit 1 USDC (1,000,000) → receive 37,000 VESC
- Burn: burn 42,000 VESC → receive ~0.9975 USDC (after 0.25% fee)

---

## Protocol Parameters (constants, not configurable)

| Parameter | Value | Meaning |
|---|---|---|
| `FEE_BPS` | 25 | 0.25% fee on burn |
| `BPS` | 10,000 | Basis point denominator |
| `MAX_RATE_CHANGE_BPS` | 2,000 | Max 20% rate movement per oracle update |
| `MAX_RATE_STALENESS` | 1,800 seconds (30 min) | mint/burn revert if rates older than this |
| `MIN_RATE_UPDATE_INTERVAL` | 600 seconds (10 min) | Minimum time between oracle pushes |

---

## Preconditions for mint() and burn()

Before calling `mint()` or `burn()`, verify all of the following or the transaction will revert:

| Check | How to verify | Revert error |
|---|---|---|
| Vault not paused | `vault.paused() == false` | `EnforcedPause` |
| Not in emergency mode | `vault.emergencyMode() == false` | `NotEmergencyMode` |
| Rates not stale | `block.timestamp - vault.lastRateUpdate() <= 1800` | `RateStale` |
| USDC approved (mint) | `usdc.allowance(user, vault) >= usdcAmount` | ERC20 transfer failure |
| VESC approved (burn) | `vesc.allowance(user, vault) >= vescAmount` | ERC20 transfer failure |
| Amount > 0 | `usdcAmount > 0` / `vescAmount > 0` | `UsdcAmountZero` / `VescAmountZero` |
| Slippage | `previewMint(amount) >= minVescOut` | `SlippageExceeded` |

---

## Reading Current State (cast commands)

```bash
# Current buy and sell rates (divide result by 1e18 to get VES/USD)
cast call 0x50F50cF026837aB49f337927d2B3269a7DEDbc60 "buyRate()(uint256)" --rpc-url https://mainnet.base.org
cast call 0x50F50cF026837aB49f337927d2B3269a7DEDbc60 "sellRate()(uint256)" --rpc-url https://mainnet.base.org

# Last rate update timestamp (unix seconds)
cast call 0x50F50cF026837aB49f337927d2B3269a7DEDbc60 "lastRateUpdate()(uint256)" --rpc-url https://mainnet.base.org

# Is vault paused?
cast call 0x50F50cF026837aB49f337927d2B3269a7DEDbc60 "paused()(bool)" --rpc-url https://mainnet.base.org

# Is emergency mode on?
cast call 0x50F50cF026837aB49f337927d2B3269a7DEDbc60 "emergencyMode()(bool)" --rpc-url https://mainnet.base.org

# USDC reserves in vault (6 decimals)
cast call 0x50F50cF026837aB49f337927d2B3269a7DEDbc60 "usdcReserves()(uint256)" --rpc-url https://mainnet.base.org

# Required reserves to back all VESC supply (6 decimals)
cast call 0x50F50cF026837aB49f337927d2B3269a7DEDbc60 "requiredReserves()(uint256)" --rpc-url https://mainnet.base.org

# Preview: how much VESC for 10 USDC (10_000_000 in 6 decimals)?
cast call 0x50F50cF026837aB49f337927d2B3269a7DEDbc60 "previewMint(uint256)(uint256)" 10000000 --rpc-url https://mainnet.base.org

# VESC total supply (18 decimals)
cast call 0xDc83741833CA8e140137a9A63B23970d55205BA0 "totalSupply()(uint256)" --rpc-url https://mainnet.base.org
```

---

## Minting VESC (step by step)

```solidity
// 1. Approve USDC spend
IERC20(USDC).approve(VAULT, usdcAmount);

// 2. Preview expected output (optional but recommended)
uint256 expectedVesc = IVault(VAULT).previewMint(usdcAmount);

// 3. Set slippage tolerance (e.g. 0.5%)
uint256 minVescOut = expectedVesc * 995 / 1000;

// 4. Mint
IVault(VAULT).mint(usdcAmount, minVescOut);
```

**Constants:**
```
VAULT = 0x50F50cF026837aB49f337927d2B3269a7DEDbc60
USDC  = 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
VESC  = 0xDc83741833CA8e140137a9A63B23970d55205BA0
```

---

## Burning VESC (step by step)

```solidity
// 1. Approve VESC spend
IERC20(VESC).approve(VAULT, vescAmount);

// 2. Preview expected output
(uint256 expectedUsdc, uint256 fee) = IVault(VAULT).previewBurn(vescAmount);

// 3. Set slippage tolerance (e.g. 0.5%)
uint256 minUsdcOut = expectedUsdc * 995 / 1000;

// 4. Burn
IVault(VAULT).burn(vescAmount, minUsdcOut);
```

---

## Oracle Setup

The oracle is a Node.js process (`oracle/rate-updater.js`) that:
1. Fetches VES/USD buy and sell rates from the Coco FX API
2. Validates the new rates are within 20% of current on-chain rates
3. Calls `setRates(newBuyRate, newSellRate)` on the vault every 15 minutes
4. Also calls `recordSample()` every cycle for on-chain chart history

**Required environment variables:**

```
FX_API_URL=           # Coco FX API endpoint URL
FX_API_KEY=           # Coco JWT bearer token
KEYSTORE_JSON=        # JSON string of encrypted ethers.js keystore for rate updater wallet
KEYSTORE_PASSWORD=    # Password to decrypt KEYSTORE_JSON
RPC_URL=              # Base RPC URL (default: https://mainnet.base.org)
```

**Keystore format:** Standard ethers.js v3 keystore JSON. Generate with:
```bash
cast wallet import <name> --interactive
# then: cat ~/.foundry/keystores/<name>
```

**Rate format for setRates():**
```javascript
// Convert float rate to uint256 wei
function rateToWei(rate) {
  const rateInt = Math.round(rate * 1e6);
  return (BigInt(rateInt) * BigInt(1e12)).toString();
}
// Example: 37000.5 VES/USD → "37000500000000000000000"
```

**Run oracle:**
```bash
cd oracle && npm install
node rate-updater.js --watch   # production: runs every 15 min
node rate-updater.js           # single run
```

---

## Deploying a Fresh Instance

```bash
# 1. Install dependencies
forge install

# 2. Set deployer key
export PRIVATE_KEY=0x...

# 3. Deploy (Base mainnet)
forge script script/Deploy.s.sol \
  --rpc-url https://mainnet.base.org \
  --broadcast \
  --verify \
  --etherscan-api-key $BASESCAN_API_KEY

# 4. Note deployed addresses from broadcast/Deploy.s.sol/8453/run-latest.json
```

**Post-deploy steps (must be done in order):**
```bash
# a. Bind vault to token (one-time, irreversible)
cast send <VESC_TOKEN> "setVault(address)" <VAULT_PROXY> --private-key $PRIVATE_KEY --rpc-url https://mainnet.base.org

# b. Renounce token ownership (vault is now the only minter/burner)
cast send <VESC_TOKEN> "renounceOwnership()" --private-key $PRIVATE_KEY --rpc-url https://mainnet.base.org

# c. Set rate updater hot wallet
cast send <VAULT_PROXY> "setRateUpdater(address)" <HOT_WALLET> --private-key $PRIVATE_KEY --rpc-url https://mainnet.base.org

# d. Approve rescue token
cast send <VAULT_PROXY> "setRescueToken(address,bool)" <USDT_ADDRESS> true --private-key $PRIVATE_KEY --rpc-url https://mainnet.base.org

# e. Start oracle and confirm first setRates() tx lands on-chain
```

---

## Upgrading the Vault

```bash
# 1. Write new implementation in src/VESCVault.sol
# 2. IMPORTANT: never remove or reorder existing storage variables
#    Only append after __gap, and reduce __gap size by slots added

# 3. Run tests
forge test

# 4. Broadcast upgrade
forge script script/Upgrade.s.sol \
  --rpc-url https://mainnet.base.org \
  --broadcast
```

Only the vault `owner()` address can authorize upgrades. The proxy address never changes.

---

## Error Reference

| Error | Cause | Fix |
|---|---|---|
| `RateStale` | `lastRateUpdate` > 30 min ago | Restart oracle, push new rates |
| `RateChangeTooLarge` | New rate > 20% from current | Check for FX API anomaly or use `owner` to override |
| `RateUpdateTooFrequent` | Called `setRates` within 10 min | Wait 10 minutes between updates |
| `SellRateExceedsBuyRate` | `sellRate > buyRate` passed to `setRates` | Verify rate order: buyRate must be > sellRate |
| `NotRateUpdater` | Caller is not `rateUpdater` or `owner` | Check wallet address matches `vault.rateUpdater()` |
| `SlippageExceeded` | Output below `minVescOut`/`minUsdcOut` | Increase slippage tolerance or reduce amount |
| `InvariantViolation` | Burn would leave vault undercollateralized | Should never happen — indicates accounting bug |
| `NotEmergencyMode` | Called emergency function while not in emergency | Call `setEmergencyMode(true)` first |
| `UsdcAmountZero` | Passed 0 to `mint()` | Pass amount > 0 |
| `VescAmountZero` | Passed 0 to `burn()` | Pass amount > 0 |
| `NoFeesToCollect` | Reserves ≤ required reserves | No surplus yet — wait for fee accumulation |

---

## Health Check

Run the full system health check locally:

```bash
node health-check.js
```

Checks: environment variables, RPC connectivity, vault state, rate freshness, reserve solvency, mint simulation, FX API reachability, oracle process status.

---

## Key Invariants (must always hold)

1. `buyRate > sellRate` — enforced by `setRates()`
2. `usdcReserves() >= requiredReserves()` — enforced after every burn by `_checkInvariant()`
3. Only vault can mint or burn VESC — enforced by `VESCToken.onlyVault`
4. Rates not older than 30 minutes during mint/burn — enforced by `MAX_RATE_STALENESS`
5. VESCToken vault address is immutable after `setVault()` — enforced by `VaultAlreadySet`
