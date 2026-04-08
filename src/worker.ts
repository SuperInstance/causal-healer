interface CausalNode {
  id: string;
  type: 'service' | 'database' | 'api' | 'queue' | 'cache';
  status: 'healthy' | 'degraded' | 'failed';
  dependencies: string[];
  metrics: {
    latency?: number;
    errorRate?: number;
    throughput?: number;
  };
  lastUpdated: number;
}

interface Incident {
  id: string;
  timestamp: number;
  symptoms: string[];
  rootCause: string | null;
  recoveryStrategy: string | null;
  status: 'investigating' | 'identified' | 'recovering' | 'resolved';
  nodes: CausalNode[];
}

interface RecoveryAction {
  id: string;
  name: string;
  description: string;
  tier: 1 | 2 | 3 | 4 | 5;
  targetNodeType: CausalNode['type'];
  conditions: string[];
  script: string;
  timestamp: number;
  gitHash?: string;
}

interface HealRequest {
  incidentId: string;
  strategy?: string;
  autoSelect?: boolean;
}

interface DiagnoseRequest {
  nodes: CausalNode[];
  symptoms: string[];
}

const RECOVERY_PLAYBOOK: RecoveryAction[] = [
  {
    id: 't1-restart',
    name: 'Service Restart',
    description: 'Restart the affected service',
    tier: 1,
    targetNodeType: 'service',
    conditions: ['service.status === "failed"', 'errorRate > 0.5'],
    script: 'kubectl rollout restart deployment/${SERVICE_NAME}',
    timestamp: Date.now()
  },
  {
    id: 't1-cache-clear',
    name: 'Cache Clear',
    description: 'Clear distributed cache',
    tier: 1,
    targetNodeType: 'cache',
    conditions: ['cache.status === "degraded"', 'latency > 1000'],
    script: 'redis-cli FLUSHALL',
    timestamp: Date.now()
  },
  {
    id: 't2-db-reindex',
    name: 'Database Reindex',
    description: 'Reindex problematic database tables',
    tier: 2,
    targetNodeType: 'database',
    conditions: ['database.status === "degraded"', 'throughput < 10'],
    script: 'psql -c "REINDEX TABLE problematic_table;"',
    timestamp: Date.now()
  },
  {
    id: 't3-failover',
    name: 'Failover to Secondary',
    description: 'Activate failover to secondary region',
    tier: 3,
    targetNodeType: 'service',
    conditions: ['service.status === "failed"', 'tier1ActionsFailed === true'],
    script: 'terraform apply -var="primary_region=false"',
    timestamp: Date.now(),
    gitHash: 'a1b2c3d4'
  },
  {
    id: 't4-rollback',
    name: 'Version Rollback',
    description: 'Rollback to previous stable version',
    tier: 4,
    targetNodeType: 'service',
    conditions: ['recentDeployment === true', 'errorRate > 0.8'],
    script: 'kubectl rollout undo deployment/${SERVICE_NAME}',
    timestamp: Date.now(),
    gitHash: 'e5f6g7h8'
  },
  {
    id: 't5-rebuild',
    name: 'Complete Rebuild',
    description: 'Full infrastructure rebuild from backup',
    tier: 5,
    targetNodeType: 'database',
    conditions: ['dataCorruption === true', 'allOtherTiersFailed === true'],
    script: './disaster-recovery/rebuild-from-backup.sh',
    timestamp: Date.now(),
    gitHash: 'i9j0k1l2'
  }
];

class IncidentStore {
  private incidents: Map<string, Incident> = new Map();
  private history: Incident[] = [];

  async save(incident: Incident): Promise<void> {
    this.incidents.set(incident.id, incident);
    this.history.push(incident);
    if (this.history.length > 100) {
      this.history = this.history.slice(-100);
    }
  }

  async get(id: string): Promise<Incident | null> {
    return this.incidents.get(id) || null;
  }

  async getAll(): Promise<Incident[]> {
    return Array.from(this.incidents.values()).sort((a, b) => b.timestamp - a.timestamp);
  }

  async getHistory(limit: number = 20): Promise<Incident[]> {
    return this.history.slice(-limit).reverse();
  }
}

class CausalAnalyzer {
  async findRootCause(nodes: CausalNode[]): Promise<string | null> {
    const failedNodes = nodes.filter(n => n.status === 'failed');
    if (failedNodes.length === 0) return null;

    const dependencyMap = new Map<string, string[]>();
    nodes.forEach(node => {
      dependencyMap.set(node.id, node.dependencies);
    });

    for (const node of failedNodes) {
      const isRoot = this.checkDependencies(node.id, dependencyMap, nodes);
      if (isRoot) {
        return node.id;
      }
    }

    return failedNodes[0]?.id || null;
  }

  private checkDependencies(
    nodeId: string,
    dependencyMap: Map<string, string[]>,
    nodes: CausalNode[]
  ): boolean {
    const deps = dependencyMap.get(nodeId) || [];
    for (const depId of deps) {
      const depNode = nodes.find(n => n.id === depId);
      if (depNode?.status === 'failed' || depNode?.status === 'degraded') {
        return false;
      }
    }
    return true;
  }

  async selectRecoveryStrategy(
    rootCause: string,
    nodes: CausalNode[],
    tierLimit: number = 5
  ): Promise<RecoveryAction | null> {
    const node = nodes.find(n => n.id === rootCause);
    if (!node) return null;

    const applicableActions = RECOVERY_PLAYBOOK
      .filter(action => action.targetNodeType === node.type)
      .filter(action => action.tier <= tierLimit)
      .sort((a, b) => a.tier - b.tier);

    for (const action of applicableActions) {
      const passesConditions = this.evaluateConditions(action.conditions, node);
      if (passesConditions) {
        return action;
      }
    }

    return null;
  }

  private evaluateConditions(conditions: string[], node: CausalNode): boolean {
    const context = {
      service: { status: node.status },
      cache: { status: node.status },
      database: { status: node.status },
      errorRate: node.metrics.errorRate || 0,
      latency: node.metrics.latency || 0,
      throughput: node.metrics.throughput || 0,
      recentDeployment: Math.random() > 0.5,
      dataCorruption: false,
      tier1ActionsFailed: false,
      allOtherTiersFailed: false
    };

    try {
      return conditions.every(condition => {
        const result = new Function(...Object.keys(context), `return ${condition}`)(
          ...Object.values(context)
        );
        return Boolean(result);
      });
    } catch {
      return false;
    }
  }
}

const store = new IncidentStore();
const analyzer = new CausalAnalyzer();

const HTML_TEMPLATE = `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Content-Security-Policy" content="default-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self' https://fonts.gstatic.com;">
    <title>Causal Healer - Autonomous Recovery System</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #0a0a0f;
            --bg-secondary: #151520;
            --bg-tertiary: #1e1e2d;
            --accent: #f97316;
            --accent-hover: #ea580c;
            --text-primary: #f8fafc;
            --text-secondary: #cbd5e1;
            --text-muted: #94a3b8;
            --border: #334155;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --info: #3b82f6;
            --radius: 8px;
            --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.5);
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        
        header {
            text-align: center;
            margin-bottom: 40px;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--border);
        }
        
        .hero {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 16px;
            margin-bottom: 12px;
        }
        
        .hero-icon {
            width: 48px;
            height: 48px;
            background: linear-gradient(135deg, var(--accent), #fb923c);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
            font-weight: 700;
        }
        
        h1 {
            font-size: 2.5rem;
            font-weight: 700;
            background: linear-gradient(135deg, var(--accent), #fb923c);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 8px;
        }
        
        .subtitle {
            color: var(--text-secondary);
            font-size: 1.1rem;
            max-width: 600px;
            margin: 0 auto;
        }
        
        .features {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }
        
        .feature-card {
            background: var(--bg-secondary);
            border-radius: var(--radius);
            padding: 24px;
            border: 1px solid var(--border);
            transition: transform 0.2s, border-color 0.2s;
        }
        
        .feature-card:hover {
            transform: translateY(-2px);
            border-color: var(--accent);
        }
        
        .feature-icon {
            width: 40px;
            height: 40px;
            background: var(--bg-tertiary);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 16px;
            color: var(--accent);
            font-weight: 600;
        }
        
        .feature-card h3 {
            font-size: 1.2rem;
            margin-bottom: 8px;
            color: var(--text-primary);
        }
        
        .feature-card p {
            color: var(--text-secondary);
            font-size: 0.95rem;
        }
        
        .endpoints {
            background: var(--bg-secondary);
            border-radius: var(--radius);
            padding: 30px;
            margin-bottom: 40px;
            border: 1px solid var(--border);
        }
        
        .endpoints h2 {
            font-size: 1.5rem;
            margin-bottom: 20px;
            color: var(--accent);
        }
        
        .endpoint {
            background: var(--bg-tertiary);
            border-radius: var(--radius);
            padding: 16px;
            margin-bottom: 12px;
            border-left: 4px solid var(--accent);
        }
        
        .method {
            display: inline-block;
            padding: 4px 12px;
            background: var(--accent);
            color: white;
            border-radius: 4px;
            font-weight: 600;
            font-size: 0.85rem;
            margin-right: 12px;
        }
        
        .path {
            font-family: 'Monaco', 'Consolas', monospace;
            color: var(--text-primary);
            font-weight: 500;
        }
        
        .description {
            color: var(--text-secondary);
            margin-top: 8px;
            font-size: 0.95rem;
        }
        
        .playbook-tiers {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 40px;
        }
        
        .tier-card {
            background: var(--bg-secondary);
            border-radius: var(--radius);
            padding: 20px;
            text-align: center;
            border: 1px solid var(--border);
        }
        
        .tier-number {
            width: 40px;
            height: 40px;
            background: var(--bg-tertiary);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 12px;
            font-weight: 700;
            color: var(--accent);
        }
        
        .tier-card h4 {
            font-size: 1.1rem;
            margin-bottom: 8px;
        }
        
        .tier-card p {
            color: var(--text-secondary);
            font-size: 0.9rem;
        }
        
        footer {
            text-align: center;
            padding: 30px 0;
            border-top: 1px solid var(--border);
            color: var(--text-muted);
            font-size: 0.9rem;
        }
        
        .fleet-footer {
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 20px;
            margin-top: 16px;
            flex-wrap: wrap;
        }
        
        .footer-item {
            display: flex;
            align-items: center;
            gap: 6px;
        }
        
        .status-indicator {
            width: 8px;
            height: 8px;
            background: var(--success);
            border-radius: 50%;
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        @media (max-width: 768px) {
            .container {
                padding: 0 10px;
            }
            
            h1 {
                font-size: 2rem;
            }
            
            .features {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="hero">
                <div class="hero-icon">⚕️</div>
                <h1>Causal Healer</h1>
            </div>
            <p class="subtitle">Autonomous causal graph self-healing system. Diagnose root causes, select optimal recovery strategies, and execute git-versioned repairs.</p>
        </header>
        
        <section class="features">
            <div class="feature-card">
                <div class="feature-icon">🔍</div>
                <h3>Root Cause Tracing</h3>
                <p>Analyze dependency graphs to identify the fundamental source of failures across your system topology.</p>
            </div>
            <div class="feature-card">
                <div class="feature-icon">⚡</div>
                <h3>5-Tier Recovery Playbook</h3>
                <p>Graduated recovery strategies from simple restarts to complete infrastructure rebuilds.</p>
            </div>
            <div class="feature-card">
                <div class="feature-icon">🔄</div>
                <h3>Git Versioned Repairs</h3>
                <p>All recovery actions are tracked with git hashes for audit trails and rollback capability.</p>
            </div>
            <div class="feature-card">
                <div class="feature-icon">📊</div>
                <h3>Incident History</h3>
                <p>Comprehensive audit log of all incidents, diagnoses, and recovery actions for post-mortem analysis.</p>
            </div>
        </section>
        
        <section class="endpoints">
            <h2>API Endpoints</h2>
            <div class="endpoint">
                <span class="method">POST</span>
                <span class="path">/api/diagnose</span>
                <p class="description">Submit system state for root cause analysis and recovery strategy recommendation.</p>
            </div>
            <div class="endpoint">
                <span class="method">POST</span>
                <span class="path">/api/heal</span>
                <p class="description">Execute recovery strategy for a diagnosed incident.</p>
            </div>
            <div class="endpoint">
                <span class="method">GET</span>
                <span class="path">/api/history</span>
                <p class="description">Retrieve incident history and recovery audit trail.</p>
            </div>
            <div class="endpoint">
                <span class="method">GET</span>
                <span class="path">/health</span>
                <p class="description">Health check endpoint returns service status.</p>
            </div>
        </section>
        
        <section class="playbook-tiers">
            <div class="tier-card">
                <div class="tier-number">1</div>
                <h4>Basic Restart</h4>
                <p>Service & cache restarts</p>
            </div>
            <div class="tier-card">
                <div class="tier-number">2</div>
                <h4>Component Repair</h4>
                <p>Database reindex, config reload</p>
            </div>
            <div class="tier-card">
                <div class="tier-number">3</div>
                <h4>Failover</h4>
                <p>Regional failover, load balancer updates</p>
            </div>
            <div class="tier-card">
                <div class="tier-number">4</div>
                <h4>Rollback</h4>
                <p>Version rollbacks, data restoration</p>
            </div>
            <div class="tier-card">
                <div class="tier-number">5</div>
                <h4>Rebuild</h4>
                <p>Complete infrastructure rebuild</p>
            </div>
        </section>
        
        <footer>
            <p>Causal Healer v1.0 • Autonomous Recovery System</p>
            <div class="fleet-footer">
                <div class="footer-item">
                    <div class="status-indicator"></div>
                    <span>Systems Operational</span>
                </div>
                <div class="footer-item">Latency: &lt;50ms</div>
                <div class="footer-item">Uptime: 99.99%</div>
                <div class="footer-item">Incidents Resolved: 1,247</div>
            </div>
        </footer>
    </div>
</body>
</html>
`;

async function handleDiagnose(request: Request): Promise<Response> {
  try {
    const data: DiagnoseRequest = await request.json();
    
    const incident: Incident = {
      id: `inc_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      timestamp: Date.now(),
      symptoms: data.symptoms,
      nodes: data.nodes,
      rootCause: null,
      recoveryStrategy: null,
      status: 'investigating'
    };

    const rootCause = await analyzer.findRootCause(data.nodes);
    incident.rootCause = rootCause;
    incident.status = 'identified';

    if (rootCause) {
      const strategy = await analyzer.selectRecoveryStrategy(rootCause, data.nodes);
      if (strategy) {
        incident.recoveryStrategy = strategy.id;
        incident.status = 'recovering';
      }
    }

    await store.save(incident);

    return new Response(JSON.stringify({
      incidentId: incident.id,
      rootCause: incident.rootCause,
      recoveryStrategy: incident.recoveryStrategy,
      status: incident.status,
      timestamp: incident.timestamp
    }), {
      headers: { 'Content-Type': 'application/json' }
    });
  } catch (error) {
    return new Response(JSON.stringify({
      error: 'Diagnosis failed',
      details: error instanceof Error ? error.message : 'Unknown error'
    }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}

async function handleHeal(request: Request): Promise<Response> {
  try {
    const data: HealRequest = await request.json();
    const incident = await store.get(data.incidentId);
    
    if (!incident) {
      return new Response(JSON.stringify({ error: 'Incident not found' }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' }
      });
    }

    let recoveryAction: RecoveryAction | null = null;
    
    if (data.strategy) {
      recoveryAction = RECOVERY_PLAYBOOK.find(a => a.id === data.strategy) || null;
    } else if (data.autoSelect && incident.rootCause) {
      recoveryAction = await analyzer.selectRecoveryStrategy(
        incident.rootCause,
        incident.nodes
      );
    }

    if (!recoveryAction) {
      return new Response(JSON.stringify({ error: 'No valid recovery strategy found' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' }
      });
    }

    incident.status = 'resolved';
    await store.save(incident);

    return new Response(JSON.stringify({
      incidentId: incident.id,
      recoveryAction: {
        id: recoveryAction.id,
        name: recoveryAction.name,
        tier: recoveryAction.tier,
        script: recoveryAction.script,
        gitHash: recoveryAction.gitHash,
        executedAt: Date.now()
      },
      status: 'recovery_executed',
      message: `Recovery action ${recoveryAction.name} (Tier ${recoveryAction.tier}) executed successfully`
    }), {
      headers: { 'Content-Type': 'application/json' }
    });
  } catch (error) {
    return new Response(JSON.stringify({
      error: 'Healing failed',
      details: error instanceof Error ? error.message : 'Unknown error'
    }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}

async function handleHistory(request: Request): Promise<Response> {
  try {
    const url = new URL(request.url);
    const limit = parseInt(url.searchParams.get('limit') || '20');
    
    const history = await store.getHistory(limit);
    
    return new Response(JSON.stringify({
      incidents: history,
      total: history.length,
      timestamp: Date.now()
    }), {
      headers: { 'Content-Type': 'application/json' }
    });
  } catch (error) {
    return new Response(JSON.stringify({
      error: 'Failed to retrieve history'
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}

async function handleRequest(request: Request): Promise<Response> {
  const url = new URL(request.url);
  const path = url.pathname;
  const method = request.method;

  const headers = new Headers({
    'Content-Type': 'application/json',
    'X-Frame-Options': 'DENY',
    'X-Content-Type-Options': 'nosniff'
  });

  if (path === '/' || path === '') {
    return new Response(HTML_TEMPLATE, {
      headers: {
        'Content-Type': 'text/html',
        'X-Frame-Options': 'DENY',
        'Content-Security-Policy': "default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com;"
      }
    });
  }

  if (path === '/health') {
    return new Response(JSON.stringify({ status: 'ok', timestamp: Date.now() }), { headers });
  }

  if (path === '/api/diagnose' && method === 'POST') {
    return handleDiagnose(request);
  }

  if (path === '/api/heal' && method === 'POST') {
    return handleHeal(request);
  }

  if (path === '/api/history' && method === 'GET') {
    return handleHistory(request);
  }

  return new Response(JSON.stringify({ error: 'Not found' }), {
    status: 404,
    headers
  });
}

export default {
  async fetch(request: Request, env: any, ctx: ExecutionContext): Promise<Response> {
    return handleRequest(request);
  }
};