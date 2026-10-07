/**
 * API client for the AEPP Planning Council & Classical Engine backend.
 */

const API_BASE = 'http://localhost:8001';

export const api = {
  /**
   * Check status of classical planners (Fast Downward, VAL, Pyperplan).
   */
  async getPDDLStatus() {
    const response = await fetch(`${API_BASE}/api/pddl-status`);
    if (!response.ok) {
      throw new Error('Failed to retrieve planner status');
    }
    return response.json();
  },

  /**
   * Run full AEPP Planning Pipeline:
   * Analysis -> 3-Stage Council Debate -> Planner Execution -> Validation -> Fallback -> Telemetry.
   */
  async solvePDDL(domainPDDL, problemPDDL, userConstraints = null) {
    const response = await fetch(`${API_BASE}/api/solve-pddl`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        domain_pddl: domainPDDL,
        problem_pddl: problemPDDL,
        user_constraints: userConstraints,
      }),
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.detail || 'Failed to solve PDDL planning problem');
    }
    return response.json();
  },

  /**
   * Retrieve historical planning telemetry records.
   */
  async getTelemetry(limit = 50, problemName = null) {
    let url = `${API_BASE}/api/telemetry?limit=${limit}`;
    if (problemName) {
      url += `&problem_name=${encodeURIComponent(problemName)}`;
    }
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error('Failed to fetch telemetry records');
    }
    return response.json();
  },

  /**
   * List all conversations (legacy chat support).
   */
  async listConversations() {
    const response = await fetch(`${API_BASE}/api/conversations`);
    if (!response.ok) {
      throw new Error('Failed to list conversations');
    }
    return response.json();
  },

  /**
   * Create a new conversation.
   */
  async createConversation() {
    const response = await fetch(`${API_BASE}/api/conversations`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({}),
    });
    if (!response.ok) {
      throw new Error('Failed to create conversation');
    }
    return response.json();
  },

  /**
   * Get a specific conversation.
   */
  async getConversation(conversationId) {
    const response = await fetch(`${API_BASE}/api/conversations/${conversationId}`);
    if (!response.ok) {
      throw new Error('Failed to get conversation');
    }
    return response.json();
  },

  /**
   * Send a message in a conversation.
   */
  async sendMessage(conversationId, content) {
    const response = await fetch(`${API_BASE}/api/conversations/${conversationId}/message`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ content }),
    });
    if (!response.ok) {
      throw new Error('Failed to send message');
    }
    return response.json();
  },
};
