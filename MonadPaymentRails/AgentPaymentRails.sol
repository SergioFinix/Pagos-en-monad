// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * AgentPaymentRails — Monad Hackathon
 * Contrato para pagos autónomos entre agentes OpenClaw via x402
 *
 * Flujo:
 *   Agente A (comprador) → llama requestService() → deposita USDC
 *   Agente B (vendedor)  → entrega el servicio off-chain
 *   Agente A             → llama confirmDelivery() → libera fondos a B
 *   Si no confirma en timeout → cualquiera llama refund()
 */

interface IERC20 {
    function transferFrom(
        address from,
        address to,
        uint256 amount
    ) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
}

contract AgentPaymentRails {
    // ─── Tipos ────────────────────────────────────────────────────────────────

    enum Status {
        Open,
        Paid,
        Delivered,
        Refunded
    }

    struct ServiceRequest {
        bytes32 id;
        address buyer; // agente comprador
        address seller; // agente vendedor
        address token; // USDC u otro ERC-20
        uint256 amount; // monto en wei del token
        string serviceSlug; // slug del endpoint x402 (ej: "analisis-monad")
        string buyerGateway; // ws://IP:PORT del comprador
        string sellerGateway; // ws://IP:PORT del vendedor
        uint256 deadline; // timestamp Unix de expiración
        Status status;
        string resultCID; // IPFS CID del resultado (lo pone el vendedor)
        uint256 createdAt;
    }

    // ─── Estado ───────────────────────────────────────────────────────────────

    mapping(bytes32 => ServiceRequest) public requests;
    bytes32[] public allRequestIds;

    uint256 public constant TIMEOUT = 1 hours;
    uint256 public feePercent = 0; // 0% fee en hackathon

    // ─── Eventos ──────────────────────────────────────────────────────────────

    event ServiceRequested(
        bytes32 indexed id,
        address indexed buyer,
        address indexed seller,
        string serviceSlug,
        uint256 amount,
        string buyerGateway,
        string sellerGateway
    );
    event ServiceDelivered(bytes32 indexed id, string resultCID);
    event PaymentReleased(bytes32 indexed id, address seller, uint256 amount);
    event PaymentRefunded(bytes32 indexed id, address buyer, uint256 amount);

    // ─── Funciones ────────────────────────────────────────────────────────────

    /**
     * Agente COMPRADOR llama esto para solicitar un servicio y depositar pago.
     * Debe haber hecho approve() al contrato antes.
     */
    function requestService(
        address seller,
        address token,
        uint256 amount,
        string calldata serviceSlug,
        string calldata buyerGateway,
        string calldata sellerGateway
    ) external returns (bytes32 id) {
        require(amount > 0, "amount must be > 0");
        require(seller != address(0), "invalid seller");

        // Genera ID único
        id = keccak256(
            abi.encodePacked(
                msg.sender,
                seller,
                serviceSlug,
                block.timestamp,
                block.number
            )
        );

        require(requests[id].createdAt == 0, "duplicate request");

        // Transfiere tokens al contrato (escrow)
        bool ok = IERC20(token).transferFrom(msg.sender, address(this), amount);
        require(ok, "token transfer failed");

        requests[id] = ServiceRequest({
            id: id,
            buyer: msg.sender,
            seller: seller,
            token: token,
            amount: amount,
            serviceSlug: serviceSlug,
            buyerGateway: buyerGateway,
            sellerGateway: sellerGateway,
            deadline: block.timestamp + TIMEOUT,
            status: Status.Paid,
            resultCID: "",
            createdAt: block.timestamp
        });

        allRequestIds.push(id);

        emit ServiceRequested(
            id,
            msg.sender,
            seller,
            serviceSlug,
            amount,
            buyerGateway,
            sellerGateway
        );
    }

    /**
     * Agente VENDEDOR registra la entrega del servicio on-chain.
     * resultCID = IPFS CID del resultado (o hash del payload)
     */
    function confirmDelivery(bytes32 id, string calldata resultCID) external {
        ServiceRequest storage req = requests[id];
        require(req.status == Status.Paid, "not in Paid state");
        require(msg.sender == req.seller, "only seller");

        req.status = Status.Delivered;
        req.resultCID = resultCID;

        emit ServiceDelivered(id, resultCID);

        // Libera el pago automáticamente al vendedor
        _releasePayout(id);
    }

    /**
     * Si el deadline pasó y el vendedor no entregó → el comprador recupera fondos.
     */
    function refund(bytes32 id) external {
        ServiceRequest storage req = requests[id];
        require(req.status == Status.Paid, "not in Paid state");
        require(block.timestamp > req.deadline, "deadline not reached");

        req.status = Status.Refunded;

        bool ok = IERC20(req.token).transfer(req.buyer, req.amount);
        require(ok, "refund transfer failed");

        emit PaymentRefunded(id, req.buyer, req.amount);
    }

    // ─── Internas ─────────────────────────────────────────────────────────────

    function _releasePayout(bytes32 id) internal {
        ServiceRequest storage req = requests[id];
        uint256 payout = req.amount;

        bool ok = IERC20(req.token).transfer(req.seller, payout);
        require(ok, "payout transfer failed");

        emit PaymentReleased(id, req.seller, payout);
    }

    // ─── Vistas ───────────────────────────────────────────────────────────────

    function getRequest(
        bytes32 id
    ) external view returns (ServiceRequest memory) {
        return requests[id];
    }

    function getAllRequests() external view returns (bytes32[] memory) {
        return allRequestIds;
    }

    function totalRequests() external view returns (uint256) {
        return allRequestIds.length;
    }
}
