/**
 * PharmaVision AI — Client API Frontend
 * Colle ce fichier dans ton frontend : src/api.js (ou src/api/index.js)
 *
 * Usage :
 *   import api from './api'
 *   const stats = await api.getStatsToday()
 *   const session = await api.startInspection({ lot_id: 1, camera_index: 0 })
 */

const BASE_URL = import.meta.env?.VITE_API_BASE_URL || "http://localhost:8000";
const WS_URL   = import.meta.env?.VITE_WS_CAMERA_URL || "ws://localhost:8000/ws/camera";
const WS_ALERTS = import.meta.env?.VITE_WS_ALERTS_URL || "ws://localhost:8000/ws/alerts";

// ── Helper fetch ────────────────────────────────────────────────────────────

async function request(method, path, body = null) {
  const options = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body) options.body = JSON.stringify(body);

  const res = await fetch(`${BASE_URL}${path}`, options);

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Erreur ${res.status}`);
  }
  return res.json();
}

const get  = (path)        => request("GET",    path);
const post = (path, body)  => request("POST",   path, body);
const put  = (path, body)  => request("PUT",    path, body);
const patch = (path, body) => request("PATCH",  path, body);
const del  = (path)        => request("DELETE", path);


// ── API ─────────────────────────────────────────────────────────────────────

const api = {

  // ── Système ──
  health: ()                  => get("/health"),

  // ── Caméras ──
  getCameras: ()              => get("/api/cameras/"),
  getSnapshot: (index)        => get(`/api/cameras/${index}/snapshot`),
  getPipelineStatus: ()       => get("/api/cameras/pipeline/status"),

  // ── Dashboard / Analytics ──
  getStatsToday: ()           => get("/api/analytics/stats/today"),
  getTrends: (days = 7)       => get(`/api/analytics/trends?days=${days}`),
  getDefectTypes: (days = 30) => get(`/api/analytics/defect-types?days=${days}`),
  getPareto: (days = 30)      => get(`/api/analytics/pareto?days=${days}`),
  getByProduct: ()            => get("/api/analytics/by-product"),
  getPerformance: (days = 7)  => get(`/api/analytics/performance?days=${days}`),

  // ── Inspection ──
  startInspection: (data) => post("/api/inspection/start", data),
  // data = { lot_id, camera_index, conformity_threshold, notes }

  stopInspection: (sessionId) => post(`/api/inspection/stop/${sessionId}`),

  processFrame: (sessionId)   => post(`/api/inspection/frame/${sessionId}`),
  // Appeler en boucle pour déclencher l'analyse + récupérer le résultat

  getLiveFrame: (sessionId)   => get(`/api/inspection/live-frame/${sessionId}`),
  // Polling leger : dernier résultat en mémoire sans re-analyser

  getActiveSessions: ()       => get("/api/inspection/active"),

  getSessions: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return get(`/api/inspection/sessions${q ? "?" + q : ""}`);
  },

  getSession: (id)            => get(`/api/inspection/sessions/${id}`),

  getResults: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return get(`/api/inspection/results${q ? "?" + q : ""}`);
  },

  // ── Produits ──
  getProducts: (search = "")  => get(`/api/products/${search ? "?search=" + search : ""}`),
  getProduct: (id)            => get(`/api/products/${id}`),
  createProduct: (data)       => post("/api/products/", data),
  updateProduct: (id, data)   => put(`/api/products/${id}`, data),
  deleteProduct: (id)         => del(`/api/products/${id}`),

  // ── Lots ──
  getLots: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return get(`/api/lots/${q ? "?" + q : ""}`);
  },
  getLot: (id)                => get(`/api/lots/${id}`),
  createLot: (data)           => post("/api/lots/", data),
  quarantineLot: (id)         => patch(`/api/lots/${id}/quarantine`),
  updateLotStatus: (id, data) => patch(`/api/lots/${id}/status`, data),
  deleteLot: (id)             => del(`/api/lots/${id}`),

  // ── Alertes ──
  getAlerts: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return get(`/api/alerts/${q ? "?" + q : ""}`);
  },
  getRecentAlerts: ()         => get("/api/alerts/recent"),
  getAlertCount: ()           => get("/api/alerts/count"),
  acknowledgeAlert: (id, comment) => patch(`/api/alerts/${id}/acknowledge`, { comment }),
  archiveAlert: (id)          => patch(`/api/alerts/${id}/archive`),
  deleteAlert: (id)           => del(`/api/alerts/${id}`),

  // ── Rapports ──
  generateReport: (data)      => post("/api/reports/generate", data),
  // data = { report_type, format, session_id?, lot_id?, period_label? }

  getReports: (page = 1)      => get(`/api/reports/?page=${page}`),
  getDownloadUrl: (id)        => `${BASE_URL}/api/reports/${id}/download`,
  deleteReport: (id)          => del(`/api/reports/${id}`),

  // ── Paramètres ──
  getSettings: ()             => get("/api/settings/"),
  updateSettings: (data)      => put("/api/settings/", data),


  // ── WebSocket caméra ──────────────────────────────────────────────────────
  /**
   * Ouvre un WebSocket pour recevoir les frames en temps réel.
   *
   * Usage dans React :
   *   const ws = api.openCameraStream(sessionId, (result) => {
   *     setFrame(result.annotated_image_b64)
   *     setScore(result.anomaly_score)
   *     setDecision(result.decision)
   *   })
   *   // Pour fermer : ws.close()
   */
  openCameraStream(sessionId, onMessage, onError) {
    const ws = new WebSocket(`${WS_URL}/${sessionId}`);

    ws.onopen = () => console.log(`[WS] Caméra connectée — session ${sessionId}`);

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage(data);
      } catch (e) {
        console.error("[WS] Erreur parsing:", e);
      }
    };

    ws.onerror = (e) => {
      console.error("[WS] Erreur caméra:", e);
      if (onError) onError(e);
    };

    ws.onclose = () => console.log(`[WS] Caméra déconnectée — session ${sessionId}`);

    return ws;
  },


  // ── WebSocket alertes ─────────────────────────────────────────────────────
  /**
   * Ouvre un WebSocket pour recevoir les alertes en temps réel.
   *
   * Usage dans React :
   *   const ws = api.openAlertsStream((alert) => {
   *     if (alert.type !== 'ping') showNotification(alert)
   *   })
   */
  openAlertsStream(onMessage, onError) {
    const ws = new WebSocket(WS_ALERTS);

    ws.onopen = () => console.log("[WS] Alertes connectées");

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage(data);
      } catch (e) {
        console.error("[WS] Erreur parsing alerte:", e);
      }
    };

    ws.onerror = (e) => {
      console.error("[WS] Erreur alertes:", e);
      if (onError) onError(e);
    };

    ws.onclose = () => console.log("[WS] Alertes déconnectées");

    return ws;
  },
};

export default api;


// ── Exemples d'utilisation dans React ────────────────────────────────────────
//
// // Dashboard
// const { total_inspected, conformity_rate } = await api.getStatsToday()
//
// // Démarrer une inspection
// const { session_id } = await api.startInspection({
//   lot_id: 3,
//   camera_index: 0,
//   conformity_threshold: 0.85
// })
//
// // Polling frame (sans WebSocket)
// const interval = setInterval(async () => {
//   const result = await api.processFrame(session_id)
//   setDecision(result.decision)
//   setImage(`data:image/jpeg;base64,${result.annotated_image_b64}`)
// }, 500)
//
// // WebSocket frame (recommandé)
// const ws = api.openCameraStream(session_id, (result) => {
//   setDecision(result.decision)
//   setScore(result.anomaly_score)
//   setImage(`data:image/jpeg;base64,${result.annotated_image_b64}`)
//   setCounters({
//     total: result.total_inspected,
//     conformes: result.total_conforme,
//     nonConformes: result.total_non_conforme,
//     taux: result.conformity_rate
//   })
// })
//
// // Afficher une image base64 dans React
// <img src={`data:image/jpeg;base64,${frame}`} alt="Inspection live" />
//
// // Arrêter
// clearInterval(interval)   // si polling
// ws.close()                // si WebSocket
// await api.stopInspection(session_id)
