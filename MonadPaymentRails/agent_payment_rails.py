#!/usr/bin/env python3
"""
agent_payment_rails.py
Interactúa con el contrato AgentPaymentRails en Monad testnet.

Uso:
  python3 agent_payment_rails.py request  <seller_addr> <slug> <amount_usdc> <seller_ws>
  python3 agent_payment_rails.py deliver  <request_id> <result_cid>
  python3 agent_payment_rails.py refund   <request_id>
  python3 agent_payment_rails.py status   <request_id>
  python3 agent_payment_rails.py list    
"""

import os, sys, json
from web3 import Web3

# ── Config ────────────────────────────────────────────────────────────────────

RPC_URL          = os.environ.get("MONAD_RPC", "https://testnet-rpc.monad.xyz")
PRIVATE_KEY      = os.environ.get("PRIVATE_KEY", "")
WALLET_ADDRESS   = os.environ.get("WALLET_ADDRESS", "")
BUYER_GATEWAY    = os.environ.get("BUYER_GATEWAY", "ws://localhost:18890")
SELLER_GATEWAY   = os.environ.get("SELLER_GATEWAY", "ws://localhost:18891")

# Contrato desplegado en Monad testnet (reemplaza tras deploy)
CONTRACT_ADDRESS = os.environ.get(
    "PAYMENT_CONTRACT",
    "0x0000000000000000000000000000000000000000"   # ← poner dirección real tras deploy
)

# USDC en Monad testnet
USDC_ADDRESS = os.environ.get(
    "USDC_ADDRESS",
    "0x534b2f3A21130d7a60830c2Df862319e593943A3"
)
USDC_DECIMALS = 6

# ABI mínimo del contrato
CONTRACT_ABI = json.loads("""[
  {
    "inputs": [
      {"name":"seller","type":"address"},
      {"name":"token","type":"address"},
      {"name":"amount","type":"uint256"},
      {"name":"serviceSlug","type":"string"},
      {"name":"buyerGateway","type":"string"},
      {"name":"sellerGateway","type":"string"}
    ],
    "name": "requestService",
    "outputs": [{"name":"id","type":"bytes32"}],
    "stateMutability": "nonpayable",
    "type": "function"
  },
  {
    "inputs": [
      {"name":"id","type":"bytes32"},
      {"name":"resultCID","type":"string"}
    ],
    "name": "confirmDelivery",
    "outputs": [],
    "stateMutability": "nonpayable",
    "type": "function"
  },
  {
    "inputs": [{"name":"id","type":"bytes32"}],
    "name": "refund",
    "outputs": [],
    "stateMutability": "nonpayable",
    "type": "function"
  },
  {
    "inputs": [{"name":"id","type":"bytes32"}],
    "name": "getRequest",
    "outputs": [{
      "components": [
        {"name":"id","type":"bytes32"},
        {"name":"buyer","type":"address"},
        {"name":"seller","type":"address"},
        {"name":"token","type":"address"},
        {"name":"amount","type":"uint256"},
        {"name":"serviceSlug","type":"string"},
        {"name":"buyerGateway","type":"string"},
        {"name":"sellerGateway","type":"string"},
        {"name":"deadline","type":"uint256"},
        {"name":"status","type":"uint8"},
        {"name":"resultCID","type":"string"},
        {"name":"createdAt","type":"uint256"}
      ],
      "type":"tuple"
    }],
    "stateMutability": "view",
    "type": "function"
  },
  {
    "inputs": [],
    "name": "getAllRequests",
    "outputs": [{"name":"","type":"bytes32[]"}],
    "stateMutability": "view",
    "type": "function"
  }
]""")

USDC_ABI = json.loads("""[
  {
    "inputs": [
      {"name":"spender","type":"address"},
      {"name":"amount","type":"uint256"}
    ],
    "name": "approve",
    "outputs": [{"name":"","type":"bool"}],
    "stateMutability": "nonpayable",
    "type": "function"
  },
  {
    "inputs": [{"name":"account","type":"address"}],
    "name": "balanceOf",
    "outputs": [{"name":"","type":"uint256"}],
    "stateMutability": "view",
    "type": "function"
  }
]""")

STATUS_MAP = {0: "Open", 1: "Paid", 2: "Delivered", 3: "Refunded"}

# ── Helpers ───────────────────────────────────────────────────────────────────

def connect():
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        print("❌ No se pudo conectar a Monad RPC:", RPC_URL)
        sys.exit(1)
    return w3

def get_account(w3):
    if not PRIVATE_KEY:
        print("❌ Falta PRIVATE_KEY en variables de entorno")
        sys.exit(1)
    return w3.eth.account.from_key(PRIVATE_KEY)

def send_tx(w3, account, fn):
    tx = fn.build_transaction({
        "from":     account.address,
        "nonce":    w3.eth.get_transaction_count(account.address),
        "gas":      500_000,
        "gasPrice": w3.eth.gas_price,
    })
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"  ⏳ TX enviada: {tx_hash.hex()}")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    if receipt.status == 1:
        print(f"  ✅ Confirmada en bloque {receipt.blockNumber}")
    else:
        print("  ❌ TX revertida")
        sys.exit(1)
    return receipt

def usdc_to_wei(amount_usdc: float) -> int:
    return int(amount_usdc * 10**USDC_DECIMALS)

def format_request(req):
    status = STATUS_MAP.get(req[9], str(req[9]))
    import datetime
    deadline = datetime.datetime.fromtimestamp(req[8]).strftime("%H:%M:%S %d/%m/%Y")
    print(f"""
  ID:            {req[0].hex()}
  Buyer:         {req[1]}
  Seller:        {req[2]}
  Service:       {req[5]}
  Amount:        {req[4] / 10**USDC_DECIMALS:.4f} USDC
  Status:        {status}
  Buyer WS:      {req[6]}
  Seller WS:     {req[7]}
  Deadline:      {deadline}
  Result CID:    {req[10] or '(pendiente)'}
""")

# ── Comandos ──────────────────────────────────────────────────────────────────

def cmd_request(w3, args):
    """Solicitar un servicio y depositar pago en escrow."""
    if len(args) < 4:
        print("Uso: request <seller_addr> <slug> <amount_usdc> <seller_ws>")
        sys.exit(1)

    seller      = w3.to_checksum_address(args[0])
    slug        = args[1]
    amount_usdc = float(args[2])
    seller_ws   = args[3]
    amount_wei  = usdc_to_wei(amount_usdc)

    account  = get_account(w3)
    usdc     = w3.eth.contract(address=w3.to_checksum_address(USDC_ADDRESS), abi=USDC_ABI)
    contract = w3.eth.contract(address=w3.to_checksum_address(CONTRACT_ADDRESS), abi=CONTRACT_ABI)

    # Verifica balance
    balance = usdc.functions.balanceOf(account.address).call()
    print(f"💰 Balance USDC: {balance / 10**USDC_DECIMALS:.4f}")
    if balance < amount_wei:
        print("❌ Balance insuficiente")
        sys.exit(1)

    # Aprueba el contrato para gastar USDC
    print(f"📝 Aprobando {amount_usdc} USDC al contrato...")
    send_tx(w3, account, usdc.functions.approve(
        w3.to_checksum_address(CONTRACT_ADDRESS), amount_wei
    ))

    # Solicita el servicio
    print(f"🚀 Solicitando servicio '{slug}' a {seller}...")
    receipt = send_tx(w3, account, contract.functions.requestService(
        seller,
        w3.to_checksum_address(USDC_ADDRESS),
        amount_wei,
        slug,
        BUYER_GATEWAY,
        seller_ws
    ))

    # Extrae el request ID del evento
    topic_sig = w3.keccak(text="ServiceRequested(bytes32,address,address,string,uint256,string,string)")
    for log in receipt.logs:
        if log.topics[0] == topic_sig:
            request_id = log.topics[1].hex()
            print(f"\n✅ Servicio solicitado!")
            print(f"   Request ID: {request_id}")
            print(f"   Guarda este ID para confirmar entrega o pedir reembolso")
            return

    print("✅ TX confirmada (no se pudo extraer el ID del evento)")

def cmd_deliver(w3, args):
    """Vendedor confirma entrega y libera el pago."""
    if len(args) < 2:
        print("Uso: deliver <request_id> <result_cid>")
        sys.exit(1)

    request_id = bytes.fromhex(args[0].removeprefix("0x"))
    result_cid = args[1]
    account    = get_account(w3)
    contract   = w3.eth.contract(address=w3.to_checksum_address(CONTRACT_ADDRESS), abi=CONTRACT_ABI)

    print(f"📦 Confirmando entrega del servicio...")
    print(f"   Result CID: {result_cid}")
    send_tx(w3, account, contract.functions.confirmDelivery(request_id, result_cid))
    print(f"💸 Pago liberado al vendedor automáticamente")

def cmd_refund(w3, args):
    """Pedir reembolso si el vendedor no entregó en tiempo."""
    if len(args) < 1:
        print("Uso: refund <request_id>")
        sys.exit(1)

    request_id = bytes.fromhex(args[0].removeprefix("0x"))
    account    = get_account(w3)
    contract   = w3.eth.contract(address=w3.to_checksum_address(CONTRACT_ADDRESS), abi=CONTRACT_ABI)

    print("💰 Solicitando reembolso...")
    send_tx(w3, account, contract.functions.refund(request_id))
    print("✅ Reembolso procesado")

def cmd_status(w3, args):
    """Ver estado de una solicitud de servicio."""
    if len(args) < 1:
        print("Uso: status <request_id>")
        sys.exit(1)

    request_id = bytes.fromhex(args[0].removeprefix("0x"))
    contract   = w3.eth.contract(address=w3.to_checksum_address(CONTRACT_ADDRESS), abi=CONTRACT_ABI)
    req        = contract.functions.getRequest(request_id).call()
    format_request(req)

def cmd_list(w3, _args):
    """Listar todas las solicitudes de servicio."""
    contract = w3.eth.contract(address=w3.to_checksum_address(CONTRACT_ADDRESS), abi=CONTRACT_ABI)
    ids      = contract.functions.getAllRequests().call()

    if not ids:
        print("No hay solicitudes registradas aún.")
        return

    print(f"\n📋 {len(ids)} solicitud(es) registradas:\n")
    for rid in ids:
        req = contract.functions.getRequest(rid).call()
        status = STATUS_MAP.get(req[9], str(req[9]))
        print(f"  [{status}] {rid.hex()} — {req[5]} — {req[4] / 10**USDC_DECIMALS:.4f} USDC")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    w3  = connect()
    cmd = sys.argv[1].lower()
    args = sys.argv[2:]

    cmds = {
        "request": cmd_request,
        "deliver": cmd_deliver,
        "refund":  cmd_refund,
        "status":  cmd_status,
        "list":    cmd_list,
    }

    if cmd not in cmds:
        print(f"Comando desconocido: {cmd}")
        print("Comandos: request | deliver | refund | status | list")
        sys.exit(1)

    cmds[cmd](w3, args)

if __name__ == "__main__":
    main()
