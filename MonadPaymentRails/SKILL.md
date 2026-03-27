---
name: agent-payment-rails
version: 1.0.0
description: |
  Infraestructura de pagos autónomos entre agentes OpenClaw via smart contract en Monad.
  Permite que un agente comprador solicite servicios a un agente vendedor, deposite USDC
  en escrow on-chain, y libere el pago automáticamente cuando el servicio es entregado.
  Usa este skill cuando el usuario quiera:
  - "pagar a otro agente por un servicio"
  - "solicitar servicio entre agentes con pago on-chain"
  - "deployar contrato de pagos entre agentes"
  - "hacer pago ws a ws entre agentes openclaw"
  - "agent to agent payment" / "a2a payment"
  - "escrow entre agentes"
  - "pago con smart contract Monad"
  - "integrar x402 con smart contract"
  - "hackathon monad pagos agentes"
  - ver estado de un pago entre agentes
  - pedir reembolso de un servicio no entregado
  - confirmar entrega de servicio y liberar pago
homepage: https://github.com/tu-usuario/agent-payment-rails
metadata:
  clawdbot:
    emoji: "🦞💸"
    os: [linux, darwin]
    requires:
      bins: [python3]
      env:
        - PRIVATE_KEY
        - WALLET_ADDRESS
        - PAYMENT_CONTRACT
        - MONAD_RPC
        - BUYER_GATEWAY
        - SELLER_GATEWAY
allowed-tools:
  - Read
  - Bash
  - Write
---

# Agent Payment Rails 🦞💸 

Smart contract en **Monad testnet** para pagos autónomos entre agentes OpenClaw.  
Permite que el agente main solicite servicios al agente vendedor con pago en escrow on-chain.

## Arquitectura

```
Agente COMPRADOR (main)          Agente VENDEDOR
ws://:18890                      ws://:18891
     │                                │
     │── requestService() ──────────▶ │  ← USDC va a escrow on-chain
     │                                │  ← Vendedor entrega servicio
     │◀── confirmDelivery() ──────────│  ← USDC liberado al vendedor
```

## Setup rápido (una vez)

### 1. Instala dependencias
```bash
pip install -r {baseDir}/requirements.txt
```

### 2. Variables de entorno requeridas
```bash
export PRIVATE_KEY="0x..."
export WALLET_ADDRESS="0x..."
export MONAD_RPC="https://testnet-rpc.monad.xyz"
export BUYER_GATEWAY="ws://158.220.98.133:18890"
export SELLER_GATEWAY="ws://158.220.98.133:18891"
```

### 3. Despliega el contrato (solo una vez)
```bash
python3 {baseDir}/scripts/deploy_contract.py
# Output: PAYMENT_CONTRACT=0x...
export PAYMENT_CONTRACT="0x..."   # guarda esto
```

Obtén MON testnet para gas: https://faucet.monad.xyz
Obtén USDC testnet: https://faucet.circle.com → selecciona Monad Testnet

---

## Comandos disponibles

### Agente COMPRADOR — Solicitar un servicio

```bash
python3 {baseDir}/scripts/agent_payment_rails.py request \
  <seller_wallet> \
  <service_slug> \
  <amount_usdc> \
  <seller_gateway_ws>
```

Ejemplo:
```bash
python3 {baseDir}/scripts/agent_payment_rails.py request \
  0xSellerWallet123... \
  "analisis-datos" \
  0.01 \
  ws://158.220.98.133:18891
```

Esto:
1. Aprueba el contrato para gastar USDC
2. Deposita el USDC en escrow on-chain
3. Emite evento `ServiceRequested` con los gateways de ambos agentes
4. Devuelve el **Request ID** — guárdalo

---

### Agente VENDEDOR — Confirmar entrega y cobrar

```bash
python3 {baseDir}/scripts/agent_payment_rails.py deliver \
  <request_id> \
  <result_cid_o_hash>
```

Ejemplo:
```bash
python3 {baseDir}/scripts/agent_payment_rails.py deliver \
  0xabc123... \
  "QmResultHash123"
```

Esto libera el USDC del escrow al vendedor automáticamente.

---

### Ver estado de un pago

```bash
python3 {baseDir}/scripts/agent_payment_rails.py status <request_id>
```

### Listar todos los pagos

```bash
python3 {baseDir}/scripts/agent_payment_rails.py list
```

### Pedir reembolso (si el vendedor no entregó en 1 hora)

```bash
python3 {baseDir}/scripts/agent_payment_rails.py refund <request_id>
```

---

## Flujo completo de demo para hackathon

```bash
# ── PASO 1: Deploy del contrato (solo una vez) ──────────────────────────────
python3 {baseDir}/scripts/deploy_contract.py
# → guarda PAYMENT_CONTRACT=0x...

# ── PASO 2: Agente main solicita servicio al agente vendedor ─────────────────
python3 {baseDir}/scripts/agent_payment_rails.py request \
  $WALLET_VENDEDOR \
  "analisis-monad" \
  0.01 \
  ws://158.220.98.133:18891
# → guarda REQUEST_ID=0x...

# ── PASO 3: (El agente vendedor entrega el servicio via x402) ────────────────
# [El vendedor ejecuta su servicio y obtiene un result hash/CID]

# ── PASO 4: Agente vendedor confirma entrega y cobra ─────────────────────────
python3 {baseDir}/scripts/agent_payment_rails.py deliver \
  $REQUEST_ID \
  "QmResultado123abc"
# → USDC liberado automáticamente al vendedor ✅

# ── PASO 5: Verifica en el explorador de Monad ───────────────────────────────
# https://testnet.monadexplorer.com/address/$PAYMENT_CONTRACT
```

---

## Referencia del contrato

Para detalles del ABI, eventos y funciones:
→ Lee `{baseDir}/references/contract-reference.md`

Para el código fuente del contrato Solidity:
→ Lee `{baseDir}/references/AgentPaymentRails.sol`

---

## Integración con x402-layer

Este skill se puede combinar con x402-layer para el flujo completo:

1. **Descubre** el servicio del vendedor en el marketplace x402
2. **Solicita** el servicio via este contrato (pago en escrow on-chain)
3. **El vendedor** entrega el resultado vía x402
4. **Confirma** la entrega → USDC liberado automáticamente

Ambos skills pueden coexistir en el mismo workspace de OpenClaw.

---

## Seguridad

- Los fondos **nunca** los toca el contrato directamente — van de buyer a escrow a seller
- El facilitador (x402-layer o Monad oficial) solo verifica firmas, no mueve USDC
- El deadline de **1 hora** protege al comprador si el vendedor no entrega
- Usa siempre wallets dedicadas para el agente con límites de fondos
