# RFC-009: Semantica VS Code Extension - SOTA 전략

**Status**: Proposed  
**Date**: 2025-12-06  
**Owner**: Semantica Core  
**Priority**: P0 (Critical)

---

## 1. Executive Summary

VS Code 확장은 **Semantica의 SOTA급 기능을 일상 코딩에 통합**하는 가교다.

**핵심 전략**:
```
Continue.dev의 오픈소스 철학 
+ Cursor의 Composer Agent UX
+ Semantica의 그래프 기반 추론
= SOTA VS Code Extension
```

**차별화 포인트**:
- CFG/DFG/PDG 기반 코드 이해 (유일)
- 그래프 안정성 기반 AI 제안 (유일)
- Dynamic Reasoning Router (비용 최적화)

---

## 2. 경쟁사 분석

### 2.1 기능 비교

| 기능 | Copilot | Cursor | Continue.dev | Cody | **Semantica** |
|------|---------|--------|--------------|------|---------------|
| 인라인 완성 | ✅ | ✅ | ✅ | ✅ | ⭐ 계획 |
| Chat | ✅ | ✅ | ✅ | ✅ | ⭐ 계획 |
| Agent Mode | ❌ | ✅ | ✅ | ❌ | ⭐ 계획 |
| 그래프 분석 | ❌ | ❌ | ❌ | ❌ | ⭐ 유일 |
| 병렬 에이전트 | ❌ | ✅ | ❌ | ❌ | 🔄 v8.1 |
| 로컬 LLM | ❌ | ❌ | ✅ | ❌ | 🔄 P2 |
| Voice | ❌ | ✅ | ❌ | ❌ | 🔄 P2 |
| 커스터마이징 | ❌ | ❌ | ✅ | ❌ | ⭐ 계획 |

### 2.2 차별화 전략

**Semantica만의 가치**:
1. **그래프 기반 제안**: "이 변경이 12개 함수에 영향" → 더 안전한 제안
2. **비용 최적화**: System 1/2 라우팅으로 60% 절감
3. **자기 반성**: 제안 전 그래프 안정성 검증

---

## 3. 아키텍처

### 3.1 전체 구조

```
┌─────────────────────────────────────────────────┐
│           VS Code Extension (Frontend)          │
│  - Inline Completion Provider                   │
│  - Chat Webview                                  │
│  - Agent Panel (Composer 스타일)                 │
│  - Quick Fix Provider                            │
│  - Code Lens Provider                            │
└────────────────┬────────────────────────────────┘
                 │ Language Server Protocol
                 │
┌────────────────▼────────────────────────────────┐
│      Semantica Language Server (Backend)        │
│  - Graph Analysis Engine                         │
│  - Dynamic Reasoning Router                      │
│  - Agent Orchestrator (v8.1)                     │
│  - Memory & Context Manager                      │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────┐
│          Semantica Core Services                │
│  (기존 v7.1 + v8.1 백엔드)                        │
└──────────────────────────────────────────────────┘
```

### 3.2 통신 방식

**옵션 1: LSP (Language Server Protocol)** ⭐ 권장
- 장점: 표준, JetBrains 확장 가능
- 단점: 양방향 통신 제약

**옵션 2: WebSocket**
- 장점: 실시간, 양방향
- 단점: 비표준

**결정**: **LSP + Custom Notifications** (하이브리드)

---

## 4. 핵심 기능 (Phase별)

### Phase 0: 기본 인프라 (Week 1-2)

#### 4.1 Extension Scaffold
```typescript
// package.json
{
  "name": "semantica-vscode",
  "displayName": "Semantica - Graph-Powered AI Coding",
  "version": "0.1.0",
  "engines": { "vscode": "^1.85.0" },
  "categories": ["AI", "Programming Languages"],
  "activationEvents": ["onStartupFinished"],
  "contributes": {
    "commands": [
      { "command": "semantica.chat", "title": "Semantica: Open Chat" },
      { "command": "semantica.agent", "title": "Semantica: Start Agent" },
      { "command": "semantica.explain", "title": "Semantica: Explain Code" },
      { "command": "semantica.fix", "title": "Semantica: Fix Issue" }
    ],
    "keybindings": [
      { "command": "semantica.chat", "key": "cmd+shift+s" },
      { "command": "semantica.agent", "key": "cmd+k" }
    ],
    "viewsContainers": {
      "activitybar": [
        { "id": "semantica", "title": "Semantica", "icon": "resources/icon.svg" }
      ]
    }
  }
}
```

#### 4.2 Language Server
```python
# src/vscode/language_server.py

from lsprotocol import types as lsp
from pygls.server import LanguageServer

class SemanticaLanguageServer(LanguageServer):
    """Semantica LSP Server"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.graph_analyzer = None  # CFG/DFG/PDG 엔진
        self.agent_orchestrator = None  # v8.1
        self.router = None  # Dynamic Reasoning
    
    async def initialize(self, params: lsp.InitializeParams):
        """초기화"""
        # 그래프 엔진 시작
        self.graph_analyzer = await init_graph_engine()
        
        return lsp.InitializeResult(
            capabilities=lsp.ServerCapabilities(
                text_document_sync=lsp.TextDocumentSyncKind.Incremental,
                completion_provider=lsp.CompletionOptions(),
                code_action_provider=True,
                code_lens_provider=lsp.CodeLensOptions(),
                hover_provider=True,
                definition_provider=True,
            )
        )
```

---

### Phase 1: 인라인 완성 (Week 3)

#### 5.1 실시간 제안

```typescript
// src/providers/completion.ts

class SemanticaCompletionProvider implements vscode.InlineCompletionItemProvider {
    async provideInlineCompletionItems(
        document: vscode.TextDocument,
        position: vscode.Position,
        context: vscode.InlineCompletionContext
    ): Promise<vscode.InlineCompletionItem[]> {
        
        // 1. 컨텍스트 수집
        const ctx = await this.gatherContext(document, position);
        
        // 2. 그래프 분석
        const graphCtx = await this.client.sendRequest('semantica/analyze', {
            fileUri: document.uri.toString(),
            position,
            includeGraph: true
        });
        
        // 3. AI 제안 요청
        const suggestions = await this.client.sendRequest('semantica/complete', {
            context: ctx,
            graphContext: graphCtx,
            model: 'fast'  // System 1
        });
        
        return suggestions.map(s => new vscode.InlineCompletionItem(s.text));
    }
    
    private async gatherContext(doc: vscode.TextDocument, pos: vscode.Position) {
        return {
            prefix: doc.getText(new vscode.Range(0, 0, pos.line, pos.character)),
            suffix: doc.getText(new vscode.Range(pos.line, pos.character, doc.lineCount, 0)),
            recentEdits: this.getRecentEdits(),
            openFiles: vscode.workspace.textDocuments.map(d => d.uri.toString()),
        };
    }
}
```

#### 5.2 그래프 기반 필터링 (차별화)

```python
# Language Server

@server.feature('semantica/complete')
async def complete(params):
    """그래프 안정성 기반 완성"""
    
    # 1. 일반 LLM 제안 (5개)
    candidates = await llm.generate_completions(params.context, n=5)
    
    # 2. 그래프 영향 분석
    scored = []
    for candidate in candidates:
        # 임시 적용
        temp_graph = apply_change(current_graph, candidate)
        
        # 안정성 점수
        stability = calculate_graph_stability(current_graph, temp_graph)
        impact = calculate_impact_radius(temp_graph)
        
        score = stability * 0.7 + (1 - impact/100) * 0.3
        scored.append((candidate, score))
    
    # 3. Top-1 반환
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[0][0]
```

**차별화**: 다른 도구는 LLM 신뢰, Semantica는 그래프 검증 ⭐

---

### Phase 2: Chat Interface (Week 4)

#### 6.1 Chat Webview

```typescript
// src/views/chat.ts

export class ChatPanel {
    private panel: vscode.WebviewPanel;
    
    constructor() {
        this.panel = vscode.window.createWebviewPanel(
            'semanticaChat',
            'Semantica Chat',
            vscode.ViewColumn.Beside,
            { enableScripts: true }
        );
        
        this.panel.webview.html = this.getWebviewContent();
        this.setupMessageHandler();
    }
    
    private setupMessageHandler() {
        this.panel.webview.onDidReceiveMessage(async (message) => {
            switch (message.command) {
                case 'sendMessage':
                    await this.handleUserMessage(message.text);
                    break;
                case 'applyDiff':
                    await this.applyCodeChange(message.diff);
                    break;
            }
        });
    }
    
    private async handleUserMessage(text: string) {
        // 1. 메시지 표시
        this.appendMessage('user', text);
        
        // 2. 컨텍스트 수집
        const context = await this.gatherWorkspaceContext();
        
        // 3. AI 응답
        const response = await this.client.sendRequest('semantica/chat', {
            message: text,
            context,
            includeGraph: true
        });
        
        // 4. 응답 표시 (스트리밍)
        this.streamResponse(response);
    }
}
```

#### 6.2 React UI (Continue.dev 스타일)

```tsx
// webview-ui/src/ChatView.tsx

import { VSCodeButton, VSCodeTextArea } from '@vscode/webview-ui-toolkit/react';

export const ChatView: React.FC = () => {
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    
    return (
        <div className="chat-container">
            <div className="messages">
                {messages.map((msg, i) => (
                    <ChatMessage key={i} message={msg} />
                ))}
            </div>
            
            {/* 그래프 인사이트 표시 (차별화) */}
            {currentInsight && (
                <GraphInsightPanel insight={currentInsight} />
            )}
            
            <div className="input-area">
                <VSCodeTextArea 
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    placeholder="Ask Semantica... (Cmd+Shift+S)"
                />
                <VSCodeButton onClick={sendMessage}>Send</VSCodeButton>
            </div>
        </div>
    );
};

const GraphInsightPanel = ({ insight }) => (
    <div className="graph-insight">
        <h4>📊 Graph Impact</h4>
        <p>This change affects {insight.impactedNodes} nodes</p>
        <p>Stability: {insight.stability * 100}%</p>
    </div>
);
```

---

### Phase 3: Agent Mode (Week 5-6)

#### 7.1 Agent Panel (Cursor Composer 스타일)

```typescript
// src/views/agent.ts

export class AgentPanel {
    private terminal: vscode.Terminal;
    private diffView: DiffViewManager;
    
    async startAgent(task: string) {
        // 1. 태스크 분석
        const plan = await this.client.sendRequest('semantica/agent/plan', {
            task,
            workspace: vscode.workspace.workspaceFolders[0].uri.toString()
        });
        
        // 2. 플랜 표시 + 승인
        const approved = await this.showPlanForApproval(plan);
        if (!approved) return;
        
        // 3. 실행 (v8.1 Agent)
        const execution = await this.client.sendRequest('semantica/agent/execute', {
            plan,
            mode: 'interactive'  // HITL
        });
        
        // 4. 실시간 업데이트
        this.streamAgentProgress(execution);
    }
    
    private streamAgentProgress(execution) {
        this.client.onNotification('semantica/agent/progress', (update) => {
            switch (update.type) {
                case 'step':
                    this.appendStep(update.step);
                    break;
                case 'file_changed':
                    this.showDiff(update.file, update.diff);
                    break;
                case 'approval_needed':
                    this.requestApproval(update.change);
                    break;
            }
        });
    }
}
```

#### 7.2 병렬 에이전트 (Cursor 스타일)

```typescript
// src/agent/parallel.ts

class ParallelAgentManager {
    private agents: Map<string, AgentInstance> = new Map();
    
    async startParallelTasks(tasks: Task[]) {
        // 최대 4개 병렬
        const slots = Math.min(tasks.length, 4);
        
        for (let i = 0; i < slots; i++) {
            const agentId = `agent-${i}`;
            this.agents.set(agentId, await this.createAgent(agentId));
        }
        
        // 병렬 실행
        await Promise.all(
            tasks.map((task, i) => 
                this.agents.get(`agent-${i % slots}`).execute(task)
            )
        );
    }
}
```

---

### Phase 4: Quick Fix & Code Actions (Week 7)

#### 8.1 Quick Fix Provider

```typescript
// src/providers/codeaction.ts

class SemanticaCodeActionProvider implements vscode.CodeActionProvider {
    async provideCodeActions(
        document: vscode.TextDocument,
        range: vscode.Range,
        context: vscode.CodeActionContext
    ): Promise<vscode.CodeAction[]> {
        
        const actions: vscode.CodeAction[] = [];
        
        // 1. 에러/경고에 대한 AI Fix
        for (const diagnostic of context.diagnostics) {
            const fix = await this.client.sendRequest('semantica/fix', {
                diagnostic,
                document: document.uri.toString(),
                range
            });
            
            if (fix) {
                const action = new vscode.CodeAction(
                    `🤖 Semantica: ${fix.title}`,
                    vscode.CodeActionKind.QuickFix
                );
                action.edit = this.createWorkspaceEdit(fix);
                actions.push(action);
            }
        }
        
        // 2. 선택 코드에 대한 제안
        if (!range.isEmpty) {
            actions.push(
                this.createRefactorAction('Optimize this code'),
                this.createRefactorAction('Add error handling'),
                this.createRefactorAction('Explain this code')
            );
        }
        
        return actions;
    }
}
```

---

### Phase 5: 고급 기능 (Week 8)

#### 9.1 Code Lens (그래프 인사이트)

```typescript
// src/providers/codelens.ts

class SemanticaCodeLensProvider implements vscode.CodeLensProvider {
    async provideCodeLenses(document: vscode.TextDocument): Promise<vscode.CodeLens[]> {
        
        // 그래프 분석
        const analysis = await this.client.sendRequest('semantica/analyze/full', {
            document: document.uri.toString()
        });
        
        const lenses: vscode.CodeLens[] = [];
        
        // 각 함수에 영향도 표시
        for (const func of analysis.functions) {
            lenses.push(new vscode.CodeLens(func.range, {
                title: `📊 Impact: ${func.impactRadius} nodes | Complexity: ${func.complexity}`,
                command: 'semantica.showImpact',
                arguments: [func.id]
            }));
        }
        
        return lenses;
    }
}
```

#### 9.2 Hover Provider (그래프 기반 설명)

```typescript
class SemanticaHoverProvider implements vscode.HoverProvider {
    async provideHover(
        document: vscode.TextDocument,
        position: vscode.Position
    ): Promise<vscode.Hover> {
        
        const symbol = await this.client.sendRequest('semantica/hover', {
            document: document.uri.toString(),
            position
        });
        
        if (!symbol) return null;
        
        const markdown = new vscode.MarkdownString();
        markdown.appendMarkdown(`**${symbol.name}**\n\n`);
        markdown.appendMarkdown(symbol.documentation + '\n\n');
        
        // 그래프 정보 추가 (차별화)
        markdown.appendMarkdown('---\n');
        markdown.appendMarkdown(`📊 **Graph Info**\n`);
        markdown.appendMarkdown(`- Called by: ${symbol.calledBy.length} functions\n`);
        markdown.appendMarkdown(`- Calls: ${symbol.calls.length} functions\n`);
        markdown.appendMarkdown(`- Impact radius: ${symbol.impactRadius} nodes\n`);
        
        return new vscode.Hover(markdown);
    }
}
```

---

## 5. 배포 전략

### 5.1 VS Code Marketplace

```json
{
  "publisher": "semantica",
  "repository": "https://github.com/semantica/vscode-extension",
  "license": "MIT",
  "pricing": "Free",
  "categories": ["AI", "Programming Languages", "Linters"],
  "keywords": ["ai", "copilot", "graph", "code-analysis", "agent"]
}
```

### 5.2 릴리스 계획

| 버전 | 기능 | 타겟 |
|------|------|------|
| 0.1.0 (Alpha) | 인라인 완성 + Chat | 내부 테스트 |
| 0.2.0 (Beta) | Agent Mode | 얼리 어답터 |
| 0.3.0 (Beta) | Quick Fix + Code Lens | 공개 베타 |
| 1.0.0 (GA) | 전체 기능 + v8.1 통합 | 일반 공개 |

---

## 6. 비용 모델

### 6.1 무료 vs 프리미엄

**Free Tier**:
- 인라인 완성 (System 1만)
- Chat (제한: 50 메시지/일)
- 기본 Quick Fix

**Pro Tier ($10/월)**:
- Agent Mode (무제한)
- System 2 추론 (ToT + Reflection)
- 병렬 에이전트 (4개)
- 그래프 인사이트 고급

**Enterprise**:
- 온프레미스 배포
- 팀 공유 메모리
- 커스텀 룰 셋
- SLA 보장

---

## 7. 성공 지표

### 7.1 채택률

- Week 1: 100 installs
- Month 1: 1,000 installs
- Month 3: 10,000 installs
- Year 1: 100,000 installs

### 7.2 품질

- 인라인 완성 수락률: 30%+
- Agent 성공률: 60%+
- 사용자 만족도: 4.5/5

---

## 8. 리스크 & 완화

| 리스크 | 확률 | 영향 | 완화 |
|--------|------|------|------|
| LSP 성능 이슈 | 중 | 높음 | 비동기 + 캐싱 |
| VS Code API 변경 | 낮 | 중 | API 버전 고정 |
| 경쟁사 기능 추격 | 높음 | 중 | 그래프 차별화 집중 |
| 서버 비용 폭증 | 중 | 높음 | System 1/2 라우팅 |

---

## 9. Next Actions

### Week 1-2: 인프라

- [ ] Extension scaffold 생성
- [ ] Language Server 기본 구조
- [ ] LSP 통신 검증
- [ ] 개발 환경 설정

### Week 3: MVP

- [ ] 인라인 완성 Provider
- [ ] 기본 Chat UI
- [ ] Alpha 릴리스

### 검증 기준

- [ ] 인라인 완성 지연 < 100ms
- [ ] Chat 응답 지연 < 2s
- [ ] 메모리 사용 < 200MB

---

## 10. 최종 결론

### 차별화 전략

```
Semantica VS Code Extension = 
  Continue.dev의 오픈 철학 +
  Cursor의 Agent UX +
  유일한 그래프 기반 추론
```

### 핵심 가치

1. **더 안전한 AI 제안** (그래프 검증)
2. **더 저렴한 비용** (Dynamic Router)
3. **더 깊은 이해** (CFG/DFG/PDG)

### 목표

**3개월 내**: Copilot 대안  
**6개월 내**: Cursor 경쟁  
**1년 내**: SOTA 확립

---

**승인 요청**: Phase 0-1 (인프라 + MVP) 즉시 착수
