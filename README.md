# VESC Protocol

**VESC** is a Venezuelan bolívar-indexed token on Base. Users deposit USDC into the vault and receive VESC tokens priced at the live VES/USD exchange rate — 1 VESC always equals 1 Venezuelan bolívar. When they redeem, they get back the USDC equivalent of their bolívares at the current rate, minus a 0.25% fee. The USD value of VESC moves with the VES/USD rate, just like holding bolívares.

> Built on Base · Powered by Coco FX rates · UUPS upgradeable · Audited dependencies (OpenZeppelin v5)

---

## Table of Contents

- [How It Works](#how-it-works)
- [Architecture](#architecture)
- [Contracts](#contracts)
- [Deployed Addresses](#deployed-addresses)
- [Rate Oracle](#rate-oracle)
- [Telegram Bot](#telegram-bot)
- [Development](#development)
- [Testing](#testing)
- [Deployment](#deployment)
- [Upgrading](#upgrading)
- [Security Model](#security-model)
- [Protocol Parameters](#protocol-parameters)
- [Emergency System](#emergency-system)
- [Progressive Decentralization](#progressive-decentralization)
- [Contributing](#contributing)

---

## How It Works

```
User deposits $1 USDC
       │
       ▼
  VESCVault.mint()
  applies sellRate (e.g. 612 VES/USD)
       │
       ▼
User receives 612 VESC
       │
       ▼  (later)
  VESCVault.burn()
  applies buyRate (e.g. 704 VES/USD)
  deducts 0.25% fee
       │
       ▼
User receives ~0.87 USDC back
```

**Two rates, one spread:**
- `sellRate` — VES per USD when minting (user gets fewer VES per dollar — unfavorable, reflects real-world buy cost)
- `buyRate` — VES per USD when burning (user needs more VESC per dollar — unfavorable, reflects real-world sell cost)
- The spread between `buyRate` and `sellRate` is the protocol margin, mirroring real FX desk economics

**Rate freshness:**
Rates expire after 30 minutes. If the oracle has not pushed a new rate, `mint()` and `burn()` revert with `RateStale`. This prevents arbitrage against stale prices.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                        Base Mainnet                      │
│                                                         │
│  ┌──────────────┐    mint/burn    ┌──────────────────┐  │
│  │  VESCToken   │◄───────────────►│   VESCVault      │  │
│  │  (ERC20)     │                 │  (ERC1967 Proxy) │  │
│  └──────────────┘                 └────────┬─────────┘  │
│                                            │setRates()  │
│                                            ▼            │
│                                   ┌─────────────────┐   │
│                                   │  Rate Updater   │   │
│                                   │  Wallet (hot)   │   │
│                                   └────────▲────────┘   │
└────────────────────────────────────────────┼────────────┘
                                             │
                              ┌──────────────┴──────────────┐
                              │      Oracle (Railway)        │
                              │   node rate-updater.js       │
                              │   fetches Coco FX API        │
                              │   every 15 minutes           │
                              └──────────────────────────────┘
```

**Key design decisions:**
- `VESCToken` ownership is renounced after deploy — only the vault can mint/burn
- `VESCVault` is UUPS upgradeable — logic can be improved without migrating funds
- Rate updater is a separate hot wallet — owner key stays cold
- 50-slot storage gap in vault for safe future upgrades

---

## Contracts

### `src/VESCToken.sol`

Minimal ERC20. Ownership is renounced after deploy; only the vault address (set once, immutable) can call `mint()` and `burn()`.

| Function | Access | Description |
|---|---|---|
| `setVault(address)` | Owner (once) | Binds vault — irreversible |
| `mint(address, uint256)` | Vault only | Mints VESC to recipient |
| `burn(address, uint256)` | Vault only | Burns VESC from holder |

### `src/VESCVault.sol`

Core protocol logic. UUPS upgradeable proxy (ERC1967).

**User functions:**

| Function | Description |
|---|---|
| `mint(uint256 usdcAmount, uint256 minVescOut)` | Deposit USDC, receive VESC at `sellRate` |
| `burn(uint256 vescAmount, uint256 minUsdcOut)` | Burn VESC, receive USDC at `buyRate` minus 0.25% fee |
| `previewMint(uint256 usdcAmount)` | View: VESC out for a given USDC deposit |
| `previewBurn(uint256 vescAmount)` | View: net USDC + fee for a given VESC burn |
| `emergencyRedeem(address token, uint256 vescAmount)` | Redeem pro-rata rescue token during emergency mode |

**Oracle functions:**

| Function | Access | Description |
|---|---|---|
| `setRates(uint256 buyRate, uint256 sellRate)` | Rate updater or owner | Push new VES/USD rates on-chain |
| `recordSample(uint256 buy, uint256 sell)` | Rate updater or owner | Emit rate sample for chart data without state change |

**Admin functions:**

| Function | Access | Description |
|---|---|---|
| `setRateUpdater(address)` | Owner | Rotate the hot wallet authorized to push rates |
| `collectFees(address)` | Owner | Sweep USDC surplus above required reserves |
| `pause() / unpause()` | Owner | Halt / resume mint and burn |
| `setEmergencyMode(bool)` | Owner | Activate emergency redemption path |
| `setRescueToken(address, bool)` | Owner | Approve token for emergency redemption |
| `swapReserves(address, address, bytes, uint256)` | Owner | Swap USDC reserves to rescue token during emergency |
| `upgradeTo(address)` | Owner | UUPS upgrade to new implementation |

---

## Deployed Addresses

**Base Mainnet (Chain ID: 8453)**

| Contract | Address |
|---|---|
| VESCVault (ERC1967 Proxy) | `0x50F50cF026837aB49f337927d2B3269a7DEDbc60` |
| VESCToken | `0xDc83741833CA8e140137a9A63B23970d55205BA0` |
| USDC | `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` |
| USDT (rescue token) | `0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2` |

**Uniswap v3 Pool**

| | |
|---|---|
| Pool (VESC/USDC 0.05%) | `0x4d717b7cd7d51e5848D1968A57014D868Bc0E7E5` |
| LP Position Token ID | `4876722` |

**Roles**

| Role | Address |
|---|---|
| Owner (cold) | `0x7f221e26628877249ace0c01b5715e3c2a4e30f9` |
| Rate Updater (hot) | `0x1fDFEB8CFB872ACfB410F980A4FdabD6a8405fe1` |

---

## Rate Oracle

The oracle (`oracle/rate-updater.js`) runs on Railway and pushes live VES/USD rates on-chain every 15 minutes.

**Flow:**
1. Fetches `crixtoRecharge` (buy) and `crixtoWithdraw` (sell) rates from Coco FX API
2. Validates rates are within 20% of current on-chain values (safety circuit breaker)
3. Calls `setRates(buyRate, sellRate)` on the vault
4. Also calls `recordSample()` every cycle for verifiable on-chain chart history

**Required environment variables:**

```bash
FX_API_URL=           # Coco FX API endpoint
FX_API_KEY=           # Coco JWT bearer token
KEYSTORE_JSON=        # Encrypted keystore JSON for rate updater wallet
KEYSTORE_PASSWORD=    # Keystore decryption password
RPC_URL=              # Base RPC (default: https://mainnet.base.org)
```

**Run locally:**
```bash
cd oracle
npm install
node rate-updater.js          # single run
node rate-updater.js --watch  # run every 15 minutes
```

**Health check:**
```bash
node health-check.js
```
Checks vault state, reserve solvency, rate freshness, FX API connectivity, and oracle process in one pass.

---

## Telegram Bot

An operator bot (`bot/bot.py`) for monitoring the protocol in real time.

**Commands:**

| Command | Description |
|---|---|
| `/rates` | Live buy/sell rates and staleness |
| `/pool` | Uniswap pool tick position, in-range status, and link |
| `/vault` | Vault reserves, VESC supply, paused/emergency state |
| `/health` | Full system health across all layers |

**Setup:**
```bash
cd bot
pip install -r requirements.txt
cp .env.example .env
# fill in TELEGRAM_TOKEN in .env
python bot.py
```

---

## Development

**Prerequisites:**
- [Foundry](https://getfoundry.sh/) — `curl -L https://foundry.paradigm.xyz | bash`
- Node.js ≥ 18 (oracle)
- Python ≥ 3.10 (bot)

**Install:**
```bash
git clone https://github.com/admin-coco/vesc-protocol
cd vesc-protocol
forge install
```

**Build:**
```bash
~/.foundry/bin/forge build
```

---

## Testing

```bash
~/.foundry/bin/forge test -vv
```

The test suite covers:
- Mint / burn at various rates
- Rate staleness enforcement
- Rate change circuit breaker (20% max)
- Minimum update interval (10 min)
- Slippage protection on mint and burn
- Reserve invariant (vault always solvent)
- Pause / unpause
- Emergency mode and pro-rata redemption
- Fee collection
- UUPS upgrade authorization
- Fuzz tests on mint→burn round trips

---

## Deployment

```bash
# Set your deployer key
export PRIVATE_KEY=...

~/.foundry/bin/forge script script/Deploy.s.sol \
  --rpc-url https://mainnet.base.org \
  --broadcast \
  --verify \
  --etherscan-api-key $BASESCAN_API_KEY
```

Post-deploy checklist:
- [ ] `VESCToken.setVault(vaultProxy)` called
- [ ] `VESCToken` ownership renounced
- [ ] `VESCVault.setRateUpdater(hotWallet)` called
- [ ] `VESCVault.setRescueToken(USDT, true)` called
- [ ] Oracle started and first `setRates()` confirmed on-chain
- [ ] Broadcast receipts saved in `broadcast/`

---

## Upgrading

The vault uses UUPS (ERC1967). Only the owner can authorize upgrades.

```bash
~/.foundry/bin/forge script script/Upgrade.s.sol \
  --rpc-url https://mainnet.base.org \
  --broadcast
```

**Storage safety rules:**
- Never remove or reorder existing storage variables
- Only append new variables after `__gap`
- Reduce `__gap` by the number of new slots added
- Test with `forge test` before broadcasting

---

## Security Model

| Threat | Mitigation |
|---|---|
| Stale price arbitrage | `MAX_RATE_STALENESS = 30 min` — mint/burn revert if oracle is silent |
| Oracle manipulation | `MAX_RATE_CHANGE_BPS = 20%` per update — large jumps revert |
| Rate spam | `MIN_RATE_UPDATE_INTERVAL = 10 min` — prevents rapid cycling |
| Hot wallet compromise | `setRateUpdater()` — owner can rotate in one tx; hot wallet cannot touch funds |
| USDC blacklist | Emergency mode + USDT rescue token — pro-rata redemption without USDC |
| Reserve deficit | `_checkInvariant()` — reverts any burn that would leave vault undercollateralized |
| Reentrancy | `ReentrancyGuard` on all state-changing user functions |
| Upgrade takeover | `onlyOwner` on `_authorizeUpgrade()` |

**Owner key** (`0x7f221e...`) controls: upgrades, fee collection, pause, emergency mode, rate updater rotation. Keep it on a hardware wallet and never expose it.

---

## Protocol Parameters

| Parameter | Value | Notes |
|---|---|---|
| `FEE_BPS` | 25 (0.25%) | Deducted from USDC on burn |
| `MAX_RATE_CHANGE_BPS` | 2000 (20%) | Max rate movement per oracle update |
| `MAX_RATE_STALENESS` | 30 minutes | After this, mint/burn revert |
| `MIN_RATE_UPDATE_INTERVAL` | 10 minutes | Minimum time between oracle pushes |
| USDC decimals | 6 | Base USDC |
| VESC decimals | 18 | Standard ERC20 |

---

## Emergency System

If USDC becomes inaccessible for any reason, the owner can:

1. Call `setRescueToken(USDT, true)` — approve alternative token
2. Call `swapReserves(USDT, router, swapData, minOut)` — swap vault USDC → USDT via any DEX
3. Call `setEmergencyMode(true)` — activates `emergencyRedeem()`
4. Users call `emergencyRedeem(USDT, vescAmount)` — receive pro-rata USDT, VESC is burned

Normal `mint()` and `burn()` are blocked during emergency mode.

---

## Progressive Decentralization

VESC launches with a pragmatic centralized structure to move fast and iterate. Decentralization is a deliberate roadmap, not an afterthought — each phase is triggered by real adoption milestones, not arbitrary timelines.

### Ownership Evolution

**Phase 1 — Single Owner (current)**
The vault owner is a single EOA (hardware wallet). This allows rapid response to bugs, oracle issues, and market events during the protocol's early life. All privileged actions — upgrades, fee collection, emergency mode, rate updater rotation — are controlled by this key.

**Phase 2 — Multi-sig (upon significant TVL)**
Once TVL reaches a meaningful threshold, ownership will be transferred to a multi-sig (e.g. Gnosis Safe with M-of-N signers). This eliminates single-point-of-failure risk and distributes trust across multiple keyholders. The `transferOwnership()` function inherited from OpenZeppelin's `OwnableUpgradeable` makes this a single transaction.

Target trigger: **$500K TVL** or community governance vote, whichever comes first.

**Phase 3 — Governance (long-term)**
At sufficient scale, ownership transitions to an on-chain governance contract — token holders vote on upgrades, fee parameters, and oracle configuration. The UUPS upgrade mechanism supports this without any fund migration.

### Oracle Evolution

The oracle is the most trust-sensitive component of the protocol. Its evolution follows a clear path from centralized to decentralized price feeds.

**Phase 1 — Single FX Provider (current)**
Rates are sourced exclusively from the Coco FX API and pushed on-chain by a single hot wallet every 15 minutes. Simple, fast, and sufficient for early adoption. Risk: single provider outage or compromise halts rate updates.

**Phase 2 — Aggregated FX Providers**
Three or more independent FX data providers (e.g. Coco, Yadio, ExchangeRate.host) are queried each cycle. The oracle computes a median or weighted average and rejects any update where providers diverge beyond a threshold. A single compromised or offline provider cannot move the on-chain rate. The `setRateUpdater()` mechanism supports swapping in an upgraded oracle without any contract changes.

**Phase 3 — Chainlink Oracle**
When Chainlink supports a VES/USD price feed on Base, the protocol migrates to it as the authoritative source. Chainlink's decentralized node network, cryptographic guarantees, and circuit breakers replace the off-chain oracle entirely. The vault upgrade path (UUPS) allows the rate-push mechanism to be replaced with a Chainlink-pull model in a single upgrade transaction, with no fund migration required.

---

## Contributing

1. Fork the repo
2. Create a branch: `git checkout -b feat/your-feature`
3. Write tests for any new behavior
4. Run `forge test` — all tests must pass
5. Open a PR against `master`

**Never commit:**
- `.env` files with real credentials
- Private keys or keystore passwords
- Oracle logs

Use `.env.example` files with placeholder values instead.

---

## License

MIT
