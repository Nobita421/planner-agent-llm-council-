/**
 * API client for the AEPP Planning Council & Classical Engine backend.
 */

const API_BASE = '';

export const api = {
  async getModels() {
    const response = await fetch(`${API_BASE}/api/models`);
    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.detail || 'Failed to load available models');
    }
    return response.json();
  },

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
   * Run full AEPP Planning Pipeline with real-time SSE progress streaming:
   * Analysis -> Stage 1 Proposals -> Stage 2 Peer Review -> Stage 3 Judge Verdict -> Execution -> Validation -> Telemetry.
   */
  async solvePDDLStream(domainPDDL, problemPDDL, userConstraints = null, onStep = () => {}, onComplete = () => {}, onError = () => {}) {
    const response = await fetch(`${API_BASE}/api/solve-pddl/stream`, {
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

    if (response.status === 404) {
      // Backend server was running an older process without reload; gracefully fallback to /api/solve-pddl
      console.warn('/api/solve-pddl/stream returned 404; falling back to /api/solve-pddl');
      onStep(2, 'Running full council planning deliberation...');
      try {
        const result = await this.solvePDDL(domainPDDL, problemPDDL, userConstraints);
        onComplete(result);
        return result;
      } catch (fallbackErr) {
        onError(fallbackErr);
        throw fallbackErr;
      }
    }

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      const errorMsg = errData.detail || 'Failed to start streaming planning pipeline';
      const err = new Error(errorMsg);
      onError(err);
      throw err;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith('data:')) {
            const jsonStr = trimmed.slice(5).trim();
            if (!jsonStr) continue;
            try {
              const event = JSON.parse(jsonStr);
              if (event.type === 'step') {
                onStep(event.step, event.detail);
              } else if (event.type === 'complete') {
                onComplete(event.data);
                return event.data;
              } else if (event.type === 'error') {
                const err = new Error(event.message || 'Error occurred during streaming planning');
                onError(err);
                throw err;
              }
            } catch (parseErr) {
              console.warn('Failed to parse SSE chunk:', jsonStr, parseErr);
            }
          }
        }
      }
    } catch (streamErr) {
      onError(streamErr);
      throw streamErr;
    }
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
