package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"
)

type SidecarServer struct {
	policyChain *PolicyChainState
	logChain    *LogChainState
	engine      *EndorsementEngine
}

func NewSidecarServer() *SidecarServer {
	return &SidecarServer{
		policyChain: NewPolicyChainState(),
		logChain:    NewLogChainState(),
		engine:      NewEndorsementEngine(),
	}
}

func (s *SidecarServer) handleHealth(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]any{
		"status":  "ok",
		"service": "fabric-gateway-sidecar",
		"time":    time.Now().UTC().Format(time.RFC3339),
	})
}

func (s *SidecarServer) handleStatus(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	cfg := s.engine.GetConfig()
	json.NewEncoder(w).Encode(map[string]any{
		"service":            "fabric-gateway-sidecar",
		"peers":              s.engine.peers,
		"peer_count":         len(s.engine.peers),
		"endorsement_policy": "AND('Org1MSP.peer','Org2MSP.peer')",
		"current_global_seq": s.policyChain.GetCurrentGlobalSeq(),
		"byzantine_config":   cfg,
	})
}

func (s *SidecarServer) handleByzantineConfig(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var req struct {
		FaultyPeer string `json:"faulty_peer"`
		Mode       string `json:"mode"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	s.engine.SetByzantineMode(req.FaultyPeer, req.Mode)
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]any{
		"status":           "configured",
		"byzantine_config": s.engine.GetConfig(),
	})
}

func (s *SidecarServer) handlePolicyCommit(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var req struct {
		PolicyID            string `json:"policy_id"`
		Hash                string `json:"hash"`
		ExpectedPrevVersion *int   `json:"expected_prev_version"`
		IssuerSig           string `json:"issuer_sig"`
		PolicyBody          any    `json:"policy_body"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	bodyBytes, _ := json.Marshal(req.PolicyBody)
	bodyStr := string(bodyBytes)

	// Step 1: Collect Endorsements from 4-peer ensemble
	currRec, _ := s.policyChain.GetPolicy(req.PolicyID)
	currV := 0
	if currRec != nil {
		currV = currRec.Version
	}
	targetV := currV + 1
	if req.ExpectedPrevVersion != nil && *req.ExpectedPrevVersion != currV {
		http.Error(w, fmt.Sprintf("INV_mono violation: expected prev version %d, got %d", *req.ExpectedPrevVersion, currV), http.StatusConflict)
		return
	}

	endorsement := s.engine.EndorseProposal(req.Hash, targetV, currV)
	if !endorsement.Satisfied {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusBadGateway)
		json.NewEncoder(w).Encode(map[string]any{
			"error":              "Endorsement policy not satisfied",
			"endorsement_result": endorsement,
		})
		return
	}

	// Step 2: Commit on-chain
	expPrev := -1
	if req.ExpectedPrevVersion != nil {
		expPrev = *req.ExpectedPrevVersion
	}
	rec, syncEv, err := s.policyChain.CommitPolicy(req.PolicyID, req.Hash, expPrev, req.IssuerSig, bodyStr, endorsement.TxID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(map[string]any{
		"new_version":        rec.Version,
		"tx_id":              rec.TxID,
		"global_seq":         syncEv.GlobalSeq,
		"hash":               rec.Hash,
		"endorsement_result": endorsement,
	})
}

func (s *SidecarServer) handlePolicyGet(w http.ResponseWriter, r *http.Request) {
	path := strings.TrimPrefix(r.URL.Path, "/policies/")
	if path == "" {
		http.Error(w, "Policy ID required", http.StatusBadRequest)
		return
	}
	rec, err := s.policyChain.GetPolicy(path)
	if err != nil {
		http.Error(w, err.Error(), http.StatusNotFound)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(rec)
}

func (s *SidecarServer) handlePolicyVersion(w http.ResponseWriter, r *http.Request) {
	path := strings.TrimPrefix(r.URL.Path, "/policies/version/")
	if path == "" {
		http.Error(w, "Policy ID required", http.StatusBadRequest)
		return
	}
	rec, err := s.policyChain.GetPolicy(path)
	ver := 0
	pHash := ""
	if err == nil && rec != nil {
		ver = rec.Version
		pHash = rec.Hash
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]any{
		"policy_id": path,
		"version":   ver,
		"hash":      pHash,
	})
}

func (s *SidecarServer) handlePolicyDelta(w http.ResponseWriter, r *http.Request) {
	fromSeqStr := r.URL.Query().Get("from_version")
	toSeqStr := r.URL.Query().Get("to_version")
	fromSeq, _ := strconv.Atoi(fromSeqStr)
	toSeq, _ := strconv.Atoi(toSeqStr)

	events := s.policyChain.GetDelta(fromSeq, toSeq)
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(events)
}

func (s *SidecarServer) handlePolicyDelete(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost && r.Method != http.MethodDelete {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	path := strings.TrimPrefix(r.URL.Path, "/policies/delete/")
	if path == "" {
		http.Error(w, "Policy ID required", http.StatusBadRequest)
		return
	}

	currRec, _ := s.policyChain.GetPolicy(path)
	currV := 0
	if currRec != nil {
		currV = currRec.Version
	}
	targetV := currV + 1

	endorsement := s.engine.EndorseProposal("DELETE", targetV, currV)
	if !endorsement.Satisfied {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusBadGateway)
		json.NewEncoder(w).Encode(map[string]any{
			"error":              "Endorsement policy not satisfied",
			"endorsement_result": endorsement,
		})
		return
	}

	rec, syncEv, err := s.policyChain.CommitPolicy(path, "", -1, "", "", endorsement.TxID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]any{
		"new_version":        rec.Version,
		"tx_id":              rec.TxID,
		"global_seq":         syncEv.GlobalSeq,
		"hash":               "",
		"event_type":         "DELETE",
		"endorsement_result": endorsement,
	})
}

func (s *SidecarServer) handleLogAppend(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var entry map[string]any
	if err := json.NewDecoder(r.Body).Decode(&entry); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	payloadBytes, _ := json.Marshal(entry)
	sum := sha256.Sum256(payloadBytes)
	txID := hex.EncodeToString(sum[:])[:16]

	rec, err := s.logChain.AppendLog(entry, txID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(rec)
}

func (s *SidecarServer) handleLogsGet(w http.ResponseWriter, r *http.Request) {
	subjectID := r.URL.Query().Get("subject_id")
	patientID := r.URL.Query().Get("patient_id")
	logs := s.logChain.GetLogs(subjectID, patientID)
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(logs)
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = os.Getenv("SIDECAR_PORT")
	}
	if port == "" {
		port = "7050"
	}

	server := NewSidecarServer()
	mux := http.NewServeMux()

	mux.HandleFunc("/health", server.handleHealth)
	mux.HandleFunc("/status", server.handleStatus)
	mux.HandleFunc("/byzantine/configure", server.handleByzantineConfig)
	mux.HandleFunc("/policies/commit", server.handlePolicyCommit)
	mux.HandleFunc("/policies/delete/", server.handlePolicyDelete)
	mux.HandleFunc("/policies/delta", server.handlePolicyDelta)
	mux.HandleFunc("/policies/version/", server.handlePolicyVersion)
	mux.HandleFunc("/policies/", server.handlePolicyGet)
	mux.HandleFunc("/logs/append", server.handleLogAppend)
	mux.HandleFunc("/logs", server.handleLogsGet)

	addr := ":" + port
	log.Printf("[Fabric Sidecar] Starting 4-peer ensemble gateway on %s...", addr)
	if err := http.ListenAndServe(addr, mux); err != nil {
		log.Fatalf("Server failed: %v", err)
	}
}
