#!/usr/bin/env python3
"""
deploy_contract.py
Despliega AgentPaymentRails en Monad testnet.

Uso: 
  python3 deploy_contract.py 

Variables requeridas:
  PRIVATE_KEY   — clave privada EVM
  MONAD_RPC     — RPC de Monad testnet (default: https://testnet-rpc.monad.xyz)

Output:
  Dirección del contrato desplegado → guárdala como PAYMENT_CONTRACT
"""

import os, sys, json, subprocess, tempfile, pathlib

RPC_URL    = os.environ.get("MONAD_RPC", "https://testnet-rpc.monad.xyz")
PRIV_KEY   = os.environ.get("PRIVATE_KEY", "")

if not PRIV_KEY:
    print("❌ Falta PRIVATE_KEY")
    sys.exit(1)

# Bytecode compilado del contrato (pre-compilado con solc 0.8.20)
# Si prefieres compilarlo tú mismo:
#   solc --bin --abi references/AgentPaymentRails.sol -o build/
# y reemplaza BYTECODE con el contenido de build/AgentPaymentRails.bin

# Para el hackathon usamos web3.py para desplegar con el source
# Requiere: pip install py-solc-x
try:
    from solcx import compile_source, install_solc
    from web3 import Web3
except ImportError:
    print("Instalando dependencias...")
    subprocess.run([sys.executable, "-m", "pip", "install",
                    "web3", "py-solc-x", "-q"], check=True)
    from solcx import compile_source, install_solc
    from web3 import Web3

# Lee el contrato
sol_path = pathlib.Path(__file__).parent.parent / "references" / "AgentPaymentRails.sol"
source   = sol_path.read_text()

print("⚙️  Compilando contrato...")
install_solc("0.8.20", show_progress=False)
compiled = compile_source(
    source,
    output_values=["abi", "bin"],
    solc_version="0.8.20"
)
contract_id  = "<stdin>:AgentPaymentRails"
contract_ifc = compiled[contract_id]
abi          = contract_ifc["abi"]
bytecode     = contract_ifc["bin"]

print("🔗 Conectando a Monad testnet...")
w3 = Web3(Web3.HTTPProvider(RPC_URL))
if not w3.is_connected():
    print(f"❌ No se pudo conectar a {RPC_URL}")
    sys.exit(1)

account = w3.eth.account.from_key(PRIV_KEY)
print(f"👛 Wallet: {account.address}")

balance = w3.eth.get_balance(account.address)
print(f"💰 Balance MON: {w3.from_wei(balance, 'ether'):.4f}")

if balance == 0:
    print("❌ Sin MON para gas. Obtén testnet MON en https://faucet.monad.xyz")
    sys.exit(1)

print("🚀 Desplegando contrato...")
Contract = w3.eth.contract(abi=abi, bytecode=bytecode)

tx = Contract.constructor().build_transaction({
    "from":     account.address,
    "nonce":    w3.eth.get_transaction_count(account.address),
    "gas":      2_000_000,
    "gasPrice": w3.eth.gas_price,
})

signed  = account.sign_transaction(tx)
tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
print(f"⏳ TX: {tx_hash.hex()}")

receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

if receipt.status == 1:
    addr = receipt.contractAddress
    print(f"\n✅ Contrato desplegado exitosamente!")
    print(f"   Dirección: {addr}")
    print(f"   Bloque:    {receipt.blockNumber}")
    print(f"   TX:        {tx_hash.hex()}")
    print(f"\n📋 Agrega esto a tu .env:")
    print(f"   PAYMENT_CONTRACT={addr}")

    # Guarda ABI
    abi_path = sol_path.parent / "AgentPaymentRails.abi.json"
    abi_path.write_text(json.dumps(abi, indent=2))
    print(f"\n📄 ABI guardado en: {abi_path}")
else:
    print("❌ Deploy fallido")
    sys.exit(1)
