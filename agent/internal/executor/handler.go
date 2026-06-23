package executor

import (
	"encoding/json"
	"io"
	"net/http"
	"time"

	"pve-aiops/agent/internal/auth"
	"pve-aiops/agent/internal/config"
)

type ExecuteRequest struct {
	RequestID      string          `json:"request_id"`
	Action         string          `json:"action"`
	Params         json.RawMessage `json:"params"`
	TimeoutSeconds int             `json:"timeout_seconds"`
}

type ExecuteResponse struct {
	RequestID  string          `json:"request_id"`
	Action     string          `json:"action"`
	Status     string          `json:"status"`
	Result     ExecutionResult `json:"result,omitempty"`
	Error      string          `json:"error,omitempty"`
	ExecutedAt string          `json:"executed_at"`
}

type Handler struct {
	cfg *config.Config
}

func NewHandler(cfg *config.Config) *Handler {
	return &Handler{cfg: cfg}
}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	reqID := r.Header.Get("X-Request-ID")
	sig := r.Header.Get("X-Signature")

	bodyBytes, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "Failed to read body", http.StatusBadRequest)
		return
	}
	defer r.Body.Close()

	signPayload := reqID + string(bodyBytes)
	
	if !auth.VerifySignature(signPayload, sig, h.cfg.PSKSecret) {
		http.Error(w, "Invalid signature", http.StatusUnauthorized)
		return
	}

	var req ExecuteRequest
	if err := json.Unmarshal(bodyBytes, &req); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	res, err := ExecuteAction(r.Context(), req.Action, req.Params)
	status := "success"
	errMsg := ""
	if err != nil {
		status = "error"
		errMsg = err.Error()
	}

	response := ExecuteResponse{
		RequestID:  req.RequestID,
		Action:     req.Action,
		Status:     status,
		Result:     res,
		Error:      errMsg,
		ExecutedAt: time.Now().Format(time.RFC3339),
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(response)
}
