## Solana network simulation

WIP simulation of Solana's network components, namely:

- Network: controls message broadcast and slot progression
- Node: staked validator nodes. Eligible for leader rotation and block voting
- Block: Basic unit of message/data to broadcast (some duration of PoH)
- BlockTransmission: <Block, Ticks> where 'ticks' represent leader transmissions of previously failed slots. Leader transmits current 'block' and a set of ticks, if any, from it's history leading up it's rotation as Leader

Simulation run/controlled from `global.py`.

### WIP/TODO
- Lockout function tuning
- Node BlockTransmission cache
- Node save/tick/vote logic
- Node stakes
- Destaking/leakage
- E&M
