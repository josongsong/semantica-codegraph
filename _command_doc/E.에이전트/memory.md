Memory Layer 완전 설계
왜 Memory가 필요한가?
현재 문제:
├── 매 세션 처음부터 시작 (학습 없음)
├── 같은 실수 반복
├── 프로젝트 컨벤션 매번 재학습
├── 이전에 해결한 비슷한 버그 기억 못함
└── 사용자 선호도 파악 못함

Memory가 있으면:
├── 과거 성공/실패 패턴 학습
├── 프로젝트별 컨텍스트 유지
├── 유사 문제 해결책 즉시 참조
├── 사용자 스타일 적응
└── 점점 더 똑똑해지는 에이전트

1. 3-Tier Memory 아키텍처
┌─────────────────────────────────────────────────────────────────┐
│                      Memory System                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────┐                                             │
│  │  Working Memory │  ← 현재 세션 (휘발성)                       │
│  │  (Short-term)   │    - 현재 태스크 상태                       │
│  │                 │    - 최근 N개 스텝 결과                     │
│  │                 │    - 활성화된 컨텍스트                       │
│  └───────┬────────┘                                             │
│          │ consolidate                                           │
│          ▼                                                       │
│  ┌────────────────┐                                             │
│  │ Episodic Memory │  ← 세션/태스크 단위 (영구 저장)             │
│  │  (Mid-term)     │    - 완료된 태스크 기록                     │
│  │                 │    - 성공/실패 에피소드                     │
│  │                 │    - 문제-해결 페어                         │
│  └───────┬────────┘                                             │
│          │ extract patterns                                      │
│          ▼                                                       │
│  ┌────────────────┐                                             │
│  │ Semantic Memory │  ← 일반화된 지식 (영구 저장)                │
│  │  (Long-term)    │    - 코드 패턴                              │
│  │                 │    - 프로젝트 규칙                          │
│  │                 │    - 버그 패턴 → 솔루션 매핑                │
│  │                 │    - 사용자 선호도                          │
│  └────────────────┘                                             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

2. Working Memory (단기 기억)
현재 세션 내 상태 관리.
typescriptinterface WorkingMemory {
  session_id: string;
  started_at: Date;
  
  // 현재 태스크
  current_task: {
    id: string;
    description: string;
    type: TaskType;
    status: TaskStatus;
    started_at: Date;
  } | null;
  
  // 실행 상태
  execution_state: {
    current_plan: Plan | null;
    current_step: number;
    steps_completed: StepRecord[];
    pending_actions: Action[];
  };
  
  // 활성 컨텍스트
  active_context: {
    files: Map<string, FileState>;        // 열린 파일들
    symbols: Map<string, SymbolInfo>;     // 참조 중인 심볼들
    hypotheses: Hypothesis[];              // 현재 가설들
    decisions: Decision[];                 // 내린 결정들
  };
  
  // 최근 결과 버퍼
  recent_buffer: {
    tool_results: CircularBuffer<ToolResult>;    // 최근 10개
    errors: CircularBuffer<ErrorRecord>;         // 최근 5개
    discoveries: CircularBuffer<Discovery>;      // 최근 10개
  };
  
  // 세션 통계
  stats: {
    tool_calls: number;
    tokens_used: number;
    errors_encountered: number;
    patches_proposed: number;
    patches_applied: number;
  };
}

class WorkingMemoryManager {
  private memory: WorkingMemory;
  private maxBufferSize = 10;

  // 2-1. 스텝 결과 기록
  recordStep(step: StepRecord): void {
    this.memory.execution_state.steps_completed.push(step);
    
    // 툴 결과 버퍼에 추가
    if (step.tool_result) {
      this.memory.recent_buffer.tool_results.push(step.tool_result);
    }
    
    // 에러 기록
    if (step.error) {
      this.memory.recent_buffer.errors.push({
        step_id: step.id,
        error: step.error,
        context: this.captureErrorContext(step),
        timestamp: new Date(),
      });
    }
    
    // 발견 사항 추출
    const discoveries = this.extractDiscoveries(step);
    for (const discovery of discoveries) {
      this.memory.recent_buffer.discoveries.push(discovery);
    }
    
    // 통계 업데이트
    this.updateStats(step);
  }

  // 2-2. 가설 관리
  addHypothesis(hypothesis: Hypothesis): void {
    // 중복 체크
    const existing = this.memory.active_context.hypotheses.find(
      h => h.description === hypothesis.description
    );
    
    if (existing) {
      // 신뢰도 업데이트
      existing.confidence = Math.max(existing.confidence, hypothesis.confidence);
      existing.evidence.push(...hypothesis.evidence);
    } else {
      this.memory.active_context.hypotheses.push(hypothesis);
    }
    
    // 상충하는 가설 처리
    this.resolveConflictingHypotheses();
  }

  updateHypothesis(id: string, update: Partial<Hypothesis>): void {
    const hypothesis = this.memory.active_context.hypotheses.find(h => h.id === id);
    if (hypothesis) {
      Object.assign(hypothesis, update);
      
      // 확정되었으면 결정으로 승격
      if (hypothesis.confidence >= 0.9 && hypothesis.status === 'confirmed') {
        this.promoteToDecision(hypothesis);
      }
      
      // 기각되었으면 제거
      if (hypothesis.status === 'rejected') {
        this.memory.active_context.hypotheses = 
          this.memory.active_context.hypotheses.filter(h => h.id !== id);
      }
    }
  }

  // 2-3. 결정 기록
  recordDecision(decision: Decision): void {
    this.memory.active_context.decisions.push({
      ...decision,
      timestamp: new Date(),
      context_snapshot: this.captureContextSnapshot(),
    });
  }

  // 2-4. 파일 상태 추적
  trackFileState(path: string, state: FileState): void {
    const existing = this.memory.active_context.files.get(path);
    
    this.memory.active_context.files.set(path, {
      ...state,
      previous_state: existing,
      access_count: (existing?.access_count || 0) + 1,
      last_accessed: new Date(),
    });
  }

  // 2-5. 컨텍스트 스냅샷
  private captureContextSnapshot(): ContextSnapshot {
    return {
      timestamp: new Date(),
      active_files: Array.from(this.memory.active_context.files.keys()),
      active_symbols: Array.from(this.memory.active_context.symbols.keys()),
      hypothesis_count: this.memory.active_context.hypotheses.length,
      decision_count: this.memory.active_context.decisions.length,
      current_step: this.memory.execution_state.current_step,
    };
  }

  // 2-6. 세션 종료 시 통합
  async consolidate(): Promise<EpisodicRecord> {
    const record: EpisodicRecord = {
      session_id: this.memory.session_id,
      task: this.memory.current_task,
      duration_ms: Date.now() - this.memory.started_at.getTime(),
      
      // 실행 요약
      execution_summary: {
        total_steps: this.memory.execution_state.steps_completed.length,
        successful_steps: this.memory.execution_state.steps_completed.filter(s => s.success).length,
        tools_used: this.aggregateToolUsage(),
        errors: this.memory.recent_buffer.errors.toArray(),
      },
      
      // 핵심 결과물
      outcomes: {
        patches_applied: this.extractAppliedPatches(),
        files_modified: Array.from(this.memory.active_context.files.entries())
          .filter(([_, state]) => state.modified)
          .map(([path, _]) => path),
        decisions: this.memory.active_context.decisions,
        discoveries: this.memory.recent_buffer.discoveries.toArray(),
      },
      
      // 학습 포인트
      learnings: await this.extractLearnings(),
      
      // 메타데이터
      metadata: {
        stats: this.memory.stats,
        final_status: this.memory.current_task?.status || 'unknown',
      },
    };
    
    return record;
  }

  // 2-7. 학습 포인트 추출
  private async extractLearnings(): Promise<Learning[]> {
    const learnings: Learning[] = [];
    
    // 에러 → 해결 패턴
    const errorResolutions = this.findErrorResolutions();
    for (const resolution of errorResolutions) {
      learnings.push({
        type: 'error_resolution',
        trigger: resolution.error,
        solution: resolution.solution,
        confidence: resolution.confidence,
      });
    }
    
    // 성공 패턴
    const successPatterns = this.findSuccessPatterns();
    for (const pattern of successPatterns) {
      learnings.push({
        type: 'success_pattern',
        context: pattern.context,
        approach: pattern.approach,
        effectiveness: pattern.effectiveness,
      });
    }
    
    // 실패 패턴 (피해야 할 것)
    const failurePatterns = this.findFailurePatterns();
    for (const pattern of failurePatterns) {
      learnings.push({
        type: 'failure_pattern',
        context: pattern.context,
        approach: pattern.approach,
        reason: pattern.reason,
      });
    }
    
    return learnings;
  }
}

3. Episodic Memory (에피소드 기억)
완료된 태스크/세션 기록.
typescriptinterface EpisodicMemory {
  // 에피소드 저장소
  episodes: EpisodeStore;
  
  // 인덱스
  indices: {
    by_task_type: Map<TaskType, string[]>;
    by_file: Map<string, string[]>;
    by_symbol: Map<string, string[]>;
    by_error_type: Map<string, string[]>;
    by_outcome: Map<'success' | 'failure' | 'partial', string[]>;
    by_date: Map<string, string[]>;  // YYYY-MM-DD
  };
  
  // 벡터 인덱스 (유사도 검색용)
  vector_index: VectorStore;
}

interface Episode {
  id: string;
  project_id: string;
  
  // 태스크 정보
  task: {
    type: TaskType;
    description: string;
    description_embedding: number[];
    complexity: number;
  };
  
  // 컨텍스트
  context: {
    files_involved: string[];
    symbols_involved: string[];
    error_types?: string[];
    stack_trace_signature?: string;
  };
  
  // 실행 과정
  execution: {
    plan_summary: string;
    steps_count: number;
    tools_used: ToolUsageSummary[];
    key_decisions: Decision[];
    pivots: Pivot[];  // 전략 변경 지점
  };
  
  // 결과
  outcome: {
    status: 'success' | 'failure' | 'partial';
    patches: PatchSummary[];
    tests_passed: boolean;
    user_feedback?: 'positive' | 'negative' | 'neutral';
  };
  
  // 추출된 지식
  extracted_knowledge: {
    problem_pattern: string;
    solution_pattern: string;
    gotchas: string[];  // 주의할 점
    tips: string[];
  };
  
  // 메타데이터
  metadata: {
    created_at: Date;
    duration_ms: number;
    tokens_used: number;
    retrieval_count: number;  // 얼마나 자주 참조되었는지
    usefulness_score: number;  // 참조 시 도움이 되었는지
  };
}

class EpisodicMemoryManager {
  private memory: EpisodicMemory;
  private embedder: Embedder;

  // 3-1. 에피소드 저장
  async store(record: EpisodicRecord): Promise<string> {
    // 임베딩 생성
    const embedding = await this.embedder.embed(
      `${record.task?.description} ${record.outcomes.decisions.map(d => d.description).join(' ')}`
    );
    
    // 에피소드 구성
    const episode: Episode = {
      id: generateId(),
      project_id: this.getCurrentProjectId(),
      
      task: {
        type: record.task?.type || 'unknown',
        description: record.task?.description || '',
        description_embedding: embedding,
        complexity: this.estimateComplexity(record),
      },
      
      context: {
        files_involved: record.outcomes.files_modified,
        symbols_involved: this.extractSymbols(record),
        error_types: record.execution_summary.errors.map(e => e.error.code),
        stack_trace_signature: this.extractStackSignature(record),
      },
      
      execution: {
        plan_summary: this.summarizePlan(record),
        steps_count: record.execution_summary.total_steps,
        tools_used: record.execution_summary.tools_used,
        key_decisions: record.outcomes.decisions,
        pivots: this.extractPivots(record),
      },
      
      outcome: {
        status: this.determineOutcome(record),
        patches: record.outcomes.patches_applied.map(p => this.summarizePatch(p)),
        tests_passed: this.checkTestsPassed(record),
      },
      
      extracted_knowledge: await this.extractKnowledge(record),
      
      metadata: {
        created_at: new Date(),
        duration_ms: record.duration_ms,
        tokens_used: record.metadata.stats.tokens_used,
        retrieval_count: 0,
        usefulness_score: 0.5,  // 초기값
      },
    };
    
    // 저장
    await this.memory.episodes.save(episode);
    
    // 인덱스 업데이트
    this.updateIndices(episode);
    
    // 벡터 인덱스 업데이트
    await this.memory.vector_index.upsert(episode.id, embedding);
    
    return episode.id;
  }

  // 3-2. 유사 에피소드 검색
  async findSimilar(query: SimilarityQuery): Promise<Episode[]> {
    const results: Episode[] = [];
    
    // 벡터 유사도 검색
    if (query.description) {
      const embedding = await this.embedder.embed(query.description);
      const similar = await this.memory.vector_index.search(embedding, query.limit || 5);
      
      for (const match of similar) {
        const episode = await this.memory.episodes.get(match.id);
        if (episode) results.push(episode);
      }
    }
    
    // 구조적 필터링
    let filtered = results;
    
    if (query.task_type) {
      filtered = filtered.filter(e => e.task.type === query.task_type);
    }
    
    if (query.files) {
      filtered = filtered.filter(e => 
        query.files!.some(f => e.context.files_involved.includes(f))
      );
    }
    
    if (query.error_type) {
      filtered = filtered.filter(e => 
        e.context.error_types?.includes(query.error_type!)
      );
    }
    
    if (query.outcome) {
      filtered = filtered.filter(e => e.outcome.status === query.outcome);
    }
    
    // 유용성 점수로 정렬
    filtered.sort((a, b) => {
      const scoreA = a.metadata.usefulness_score * (1 + Math.log(a.metadata.retrieval_count + 1));
      const scoreB = b.metadata.usefulness_score * (1 + Math.log(b.metadata.retrieval_count + 1));
      return scoreB - scoreA;
    });
    
    // 검색 카운트 업데이트
    for (const episode of filtered.slice(0, query.limit || 5)) {
      episode.metadata.retrieval_count++;
      await this.memory.episodes.save(episode);
    }
    
    return filtered.slice(0, query.limit || 5);
  }

  // 3-3. 에러 패턴으로 검색
  async findByErrorPattern(error: ErrorInfo): Promise<Episode[]> {
    const signature = this.computeErrorSignature(error);
    
    // 정확히 일치하는 에러
    const exactMatches = await this.memory.episodes.findByIndex(
      'by_error_type',
      error.code
    );
    
    // 스택 트레이스 패턴 매칭
    const stackMatches = await this.findByStackPattern(error.stack_trace);
    
    // 병합 및 중복 제거
    const all = [...exactMatches, ...stackMatches];
    const unique = this.deduplicateEpisodes(all);
    
    // 성공한 에피소드 우선
    unique.sort((a, b) => {
      if (a.outcome.status === 'success' && b.outcome.status !== 'success') return -1;
      if (a.outcome.status !== 'success' && b.outcome.status === 'success') return 1;
      return b.metadata.usefulness_score - a.metadata.usefulness_score;
    });
    
    return unique;
  }

  // 3-4. 지식 추출
  private async extractKnowledge(record: EpisodicRecord): Promise<ExtractedKnowledge> {
    // LLM으로 패턴 추출
    const prompt = `Analyze this coding task execution and extract reusable knowledge.

Task: ${record.task?.description}
Steps taken: ${record.execution_summary.total_steps}
Outcome: ${record.metadata.final_status}
Key decisions: ${record.outcomes.decisions.map(d => d.description).join('; ')}
Errors encountered: ${record.execution_summary.errors.map(e => e.error.message).join('; ')}

Extract:
1. Problem pattern (what kind of problem was this?)
2. Solution pattern (what approach worked/didn't work?)
3. Gotchas (what unexpected issues came up?)
4. Tips (what would you do differently next time?)

Respond in JSON format.`;

    const response = await this.llm.complete(prompt);
    return JSON.parse(response);
  }

  // 3-5. 유용성 피드백
  async recordFeedback(episodeId: string, feedback: EpisodeFeedback): void {
    const episode = await this.memory.episodes.get(episodeId);
    if (!episode) return;
    
    // 유용성 점수 업데이트 (이동 평균)
    const alpha = 0.3;  // 학습률
    const feedbackScore = feedback.helpful ? 1.0 : 0.0;
    episode.metadata.usefulness_score = 
      alpha * feedbackScore + (1 - alpha) * episode.metadata.usefulness_score;
    
    // 사용자 피드백 기록
    if (feedback.user_feedback) {
      episode.outcome.user_feedback = feedback.user_feedback;
    }
    
    await this.memory.episodes.save(episode);
    
    // 패턴 강화/약화
    if (feedback.helpful) {
      await this.reinforcePatterns(episode);
    } else {
      await this.weakenPatterns(episode);
    }
  }
}

4. Semantic Memory (의미 기억)
일반화된 지식과 패턴.
typescriptinterface SemanticMemory {
  // 버그 패턴 → 솔루션
  bug_patterns: PatternStore<BugPattern>;
  
  // 코드 패턴 (리팩토링, 최적화 등)
  code_patterns: PatternStore<CodePattern>;
  
  // 프로젝트 지식
  project_knowledge: Map<string, ProjectKnowledge>;
  
  // 사용자 선호도
  user_preferences: UserPreferences;
  
  // 도구 사용 패턴
  tool_patterns: ToolPatternStore;
}

// 4-1. 버그 패턴
interface BugPattern {
  id: string;
  
  // 식별 정보
  signature: {
    error_types: string[];
    error_message_patterns: RegExp[];
    stack_trace_patterns: string[];
    code_patterns: string[];  // AST 패턴
  };
  
  // 컨텍스트
  typical_context: {
    file_types: string[];
    frameworks: string[];
    common_causes: string[];
  };
  
  // 솔루션
  solutions: Array<{
    description: string;
    approach: string;
    code_template?: string;
    success_rate: number;
    applicability_conditions: string[];
  }>;
  
  // 통계
  stats: {
    occurrence_count: number;
    resolution_count: number;
    avg_resolution_time_ms: number;
    last_seen: Date;
  };
  
  // 연관 패턴
  related_patterns: string[];
}

// 4-2. 코드 패턴
interface CodePattern {
  id: string;
  name: string;
  category: 'refactoring' | 'optimization' | 'security' | 'style' | 'architecture';
  
  // 패턴 인식
  detection: {
    ast_pattern?: string;
    code_smell?: string;
    metrics_threshold?: Record<string, number>;
  };
  
  // 변환
  transformation: {
    description: string;
    before_template: string;
    after_template: string;
    variables: string[];
  };
  
  // 적용 조건
  applicability: {
    languages: string[];
    min_complexity?: number;
    max_complexity?: number;
    prerequisites: string[];
    contraindications: string[];  // 적용하면 안 되는 경우
  };
  
  // 효과
  effects: {
    readability: number;      // -1 to 1
    performance: number;
    maintainability: number;
    testability: number;
  };
  
  // 통계
  stats: {
    application_count: number;
    success_rate: number;
    avg_improvement: number;
  };
}

// 4-3. 프로젝트 지식
interface ProjectKnowledge {
  project_id: string;
  
  // 구조
  structure: {
    architecture_type: string;  // 'monolith', 'microservices', etc.
    main_directories: DirectoryInfo[];
    entry_points: string[];
    config_files: string[];
  };
  
  // 컨벤션
  conventions: {
    naming: NamingConventions;
    file_organization: string;
    import_style: string;
    testing_patterns: string[];
    documentation_style: string;
  };
  
  // 기술 스택
  tech_stack: {
    languages: string[];
    frameworks: string[];
    testing_frameworks: string[];
    build_tools: string[];
    dependencies: DependencyInfo[];
  };
  
  // 핫스팟
  hotspots: {
    frequently_modified: string[];
    high_complexity: string[];
    bug_prone: string[];
    critical_paths: string[];
  };
  
  // 팀 지식
  team_knowledge: {
    common_issues: string[];
    preferred_solutions: Record<string, string>;
    avoid_patterns: string[];
    review_focus: string[];
  };
  
  // 통계
  stats: {
    total_sessions: number;
    total_tasks: number;
    success_rate: number;
    common_task_types: Record<TaskType, number>;
    last_updated: Date;
  };
}

// 4-4. 사용자 선호도
interface UserPreferences {
  // 코딩 스타일
  coding_style: {
    verbosity: 'minimal' | 'moderate' | 'detailed';
    comment_style: 'none' | 'minimal' | 'extensive';
    variable_naming: 'short' | 'descriptive';
    function_size: 'small' | 'medium' | 'large';
  };
  
  // 상호작용 스타일
  interaction_style: {
    explanation_depth: 'brief' | 'moderate' | 'thorough';
    confirmation_frequency: 'always' | 'important' | 'rarely';
    proactivity: 'reactive' | 'moderate' | 'proactive';
  };
  
  // 도구 선호
  tool_preferences: {
    preferred_test_approach: 'tdd' | 'after' | 'minimal';
    patch_style: 'minimal' | 'comprehensive';
    refactoring_aggressiveness: 'conservative' | 'moderate' | 'aggressive';
  };
  
  // 학습된 패턴
  learned_patterns: {
    frequently_accepted: string[];    // 자주 수락한 제안
    frequently_rejected: string[];    // 자주 거절한 제안
    custom_shortcuts: Record<string, string>;  // 사용자 정의 명령
  };
}

class SemanticMemoryManager {
  private memory: SemanticMemory;
  private patternMatcher: PatternMatcher;

  // 4-5. 버그 패턴 매칭
  async matchBugPattern(error: ErrorInfo, context: CodeContext): Promise<BugPatternMatch[]> {
    const matches: BugPatternMatch[] = [];
    
    // 에러 타입으로 후보 필터링
    const candidates = await this.memory.bug_patterns.findByErrorType(error.code);
    
    for (const pattern of candidates) {
      const score = this.calculatePatternMatchScore(pattern, error, context);
      
      if (score > 0.5) {
        matches.push({
          pattern,
          score,
          matched_aspects: this.getMatchedAspects(pattern, error, context),
          recommended_solution: this.selectBestSolution(pattern, context),
        });
      }
    }
    
    // 점수순 정렬
    matches.sort((a, b) => b.score - a.score);
    
    return matches;
  }

  // 4-6. 패턴 학습/업데이트
  async learnFromEpisode(episode: Episode): Promise<void> {
    // 새로운 버그 패턴 추출
    if (episode.context.error_types && episode.outcome.status === 'success') {
      await this.learnBugPattern(episode);
    }
    
    // 코드 패턴 학습
    if (episode.execution.key_decisions.some(d => d.type === 'refactoring')) {
      await this.learnCodePattern(episode);
    }
    
    // 프로젝트 지식 업데이트
    await this.updateProjectKnowledge(episode);
    
    // 사용자 선호도 업데이트
    await this.updateUserPreferences(episode);
  }

  // 4-7. 버그 패턴 학습
  private async learnBugPattern(episode: Episode): Promise<void> {
    for (const errorType of episode.context.error_types || []) {
      // 기존 패턴 찾기
      let pattern = await this.memory.bug_patterns.findBySignature(
        errorType,
        episode.context.stack_trace_signature
      );
      
      if (pattern) {
        // 기존 패턴 강화
        pattern.stats.occurrence_count++;
        pattern.stats.resolution_count++;
        pattern.stats.last_seen = new Date();
        
        // 새로운 솔루션 추가 또는 기존 솔루션 강화
        const solutionDesc = episode.extracted_knowledge.solution_pattern;
        const existingSolution = pattern.solutions.find(
          s => this.isSimilarSolution(s.description, solutionDesc)
        );
        
        if (existingSolution) {
          existingSolution.success_rate = this.updateSuccessRate(
            existingSolution.success_rate,
            true
          );
        } else {
          pattern.solutions.push({
            description: solutionDesc,
            approach: episode.execution.plan_summary,
            success_rate: 1.0,
            applicability_conditions: [],
          });
        }
      } else {
        // 새 패턴 생성
        pattern = {
          id: generateId(),
          signature: {
            error_types: [errorType],
            error_message_patterns: [],
            stack_trace_patterns: [episode.context.stack_trace_signature || ''],
            code_patterns: [],
          },
          typical_context: {
            file_types: this.extractFileTypes(episode.context.files_involved),
            frameworks: [],
            common_causes: [episode.extracted_knowledge.problem_pattern],
          },
          solutions: [{
            description: episode.extracted_knowledge.solution_pattern,
            approach: episode.execution.plan_summary,
            success_rate: 1.0,
            applicability_conditions: [],
          }],
          stats: {
            occurrence_count: 1,
            resolution_count: 1,
            avg_resolution_time_ms: episode.metadata.duration_ms,
            last_seen: new Date(),
          },
          related_patterns: [],
        };
      }
      
      await this.memory.bug_patterns.save(pattern);
    }
  }

  // 4-8. 프로젝트 지식 업데이트
  private async updateProjectKnowledge(episode: Episode): Promise<void> {
    let knowledge = this.memory.project_knowledge.get(episode.project_id);
    
    if (!knowledge) {
      knowledge = this.initializeProjectKnowledge(episode.project_id);
    }
    
    // 핫스팟 업데이트
    for (const file of episode.context.files_involved) {
      if (!knowledge.hotspots.frequently_modified.includes(file)) {
        knowledge.hotspots.frequently_modified.push(file);
      }
    }
    
    // 버그 발생 파일 추적
    if (episode.context.error_types?.length) {
      for (const file of episode.context.files_involved) {
        if (!knowledge.hotspots.bug_prone.includes(file)) {
          knowledge.hotspots.bug_prone.push(file);
        }
      }
    }
    
    // 통계 업데이트
    knowledge.stats.total_sessions++;
    knowledge.stats.total_tasks++;
    if (episode.outcome.status === 'success') {
      knowledge.stats.success_rate = this.updateMovingAverage(
        knowledge.stats.success_rate,
        1.0,
        knowledge.stats.total_tasks
      );
    }
    knowledge.stats.common_task_types[episode.task.type] = 
      (knowledge.stats.common_task_types[episode.task.type] || 0) + 1;
    knowledge.stats.last_updated = new Date();
    
    // gotchas 추가
    for (const gotcha of episode.extracted_knowledge.gotchas) {
      if (!knowledge.team_knowledge.common_issues.includes(gotcha)) {
        knowledge.team_knowledge.common_issues.push(gotcha);
      }
    }
    
    this.memory.project_knowledge.set(episode.project_id, knowledge);
  }

  // 4-9. 사용자 선호도 학습
  private async updateUserPreferences(episode: Episode): Promise<void> {
    const prefs = this.memory.user_preferences;
    
    // 결정 패턴 분석
    for (const decision of episode.execution.key_decisions) {
      if (decision.accepted) {
        // 수락된 패턴 기록
        const pattern = this.extractDecisionPattern(decision);
        if (!prefs.learned_patterns.frequently_accepted.includes(pattern)) {
          prefs.learned_patterns.frequently_accepted.push(pattern);
        }
      } else {
        // 거절된 패턴 기록
        const pattern = this.extractDecisionPattern(decision);
        if (!prefs.learned_patterns.frequently_rejected.includes(pattern)) {
          prefs.learned_patterns.frequently_rejected.push(pattern);
        }
      }
    }
    
    // 코딩 스타일 추론
    const styleIndicators = this.analyzeCodeStyle(episode);
    this.updateStylePreferences(prefs, styleIndicators);
  }

  // 4-10. 컨텍스트 기반 지식 검색
  async getRelevantKnowledge(context: TaskContext): Promise<RelevantKnowledge> {
    const projectKnowledge = this.memory.project_knowledge.get(context.project_id);
    
    return {
      // 프로젝트 컨벤션
      conventions: projectKnowledge?.conventions,
      
      // 관련 버그 패턴
      relevant_bug_patterns: context.error 
        ? await this.matchBugPattern(context.error, context.code_context)
        : [],
      
      // 적용 가능한 코드 패턴
      applicable_code_patterns: await this.findApplicableCodePatterns(context),
      
      // 사용자 선호도
      user_preferences: this.memory.user_preferences,
      
      // 프로젝트 핫스팟
      hotspots: projectKnowledge?.hotspots,
      
      // 팀 지식 (주의사항 등)
      team_knowledge: projectKnowledge?.team_knowledge,
      
      // 추천 접근법
      recommended_approach: this.recommendApproach(context, projectKnowledge),
    };
  }
}

5. Memory Retrieval System
적절한 시점에 적절한 기억을 가져온다.
typescriptclass MemoryRetrievalSystem {
  private workingMemory: WorkingMemoryManager;
  private episodicMemory: EpisodicMemoryManager;
  private semanticMemory: SemanticMemoryManager;

  // 5-1. 태스크 시작 시 관련 기억 로드
  async loadRelevantMemories(task: Task): Promise<LoadedMemories> {
    const [
      similarEpisodes,
      bugPatterns,
      projectKnowledge,
      userPrefs
    ] = await Promise.all([
      this.episodicMemory.findSimilar({
        description: task.description,
        task_type: task.type,
        limit: 3,
      }),
      task.error 
        ? this.semanticMemory.matchBugPattern(task.error, task.context)
        : [],
      this.semanticMemory.getProjectKnowledge(task.project_id),
      this.semanticMemory.getUserPreferences(),
    ]);
    
    return {
      similar_episodes: similarEpisodes,
      bug_patterns: bugPatterns,
      project_knowledge: projectKnowledge,
      user_preferences: userPrefs,
      
      // 종합 가이던스 생성
      guidance: this.synthesizeGuidance(
        similarEpisodes,
        bugPatterns,
        projectKnowledge,
        userPrefs,
        task
      ),
    };
  }

  // 5-2. 실행 중 기억 쿼리
  async queryDuringExecution(query: ExecutionQuery): Promise<MemoryQueryResult> {
    switch (query.type) {
      case 'similar_error':
        return this.handleSimilarErrorQuery(query);
      
      case 'how_to':
        return this.handleHowToQuery(query);
      
      case 'convention':
        return this.handleConventionQuery(query);
      
      case 'past_approach':
        return this.handlePastApproachQuery(query);
      
      default:
        return this.handleGeneralQuery(query);
    }
  }

  // 5-3. 유사 에러 쿼리 처리
  private async handleSimilarErrorQuery(query: ExecutionQuery): Promise<MemoryQueryResult> {
    const error = query.context.error;
    
    // 1. 현재 세션에서 같은 에러 찾기
    const recentErrors = this.workingMemory.getRecentErrors();
    const sameErrorInSession = recentErrors.find(e => e.error.code === error.code);
    
    if (sameErrorInSession) {
      return {
        source: 'working_memory',
        result: {
          message: "This error occurred earlier in this session",
          previous_attempt: sameErrorInSession,
          suggestion: "Try a different approach",
        },
      };
    }
    
    // 2. Episodic memory에서 찾기
    const episodes = await this.episodicMemory.findByErrorPattern(error);
    
    if (episodes.length > 0) {
      const bestEpisode = episodes[0];
      return {
        source: 'episodic_memory',
        result: {
          message: "Found similar error in past sessions",
          episode: bestEpisode,
          solution_used: bestEpisode.extracted_knowledge.solution_pattern,
          success: bestEpisode.outcome.status === 'success',
        },
      };
    }
    
    // 3. Semantic memory에서 패턴 찾기
    const patterns = await this.semanticMemory.matchBugPattern(error, query.context);
    
    if (patterns.length > 0) {
      return {
        source: 'semantic_memory',
        result: {
          message: "Found matching bug pattern",
          pattern: patterns[0].pattern,
          recommended_solution: patterns[0].recommended_solution,
          confidence: patterns[0].score,
        },
      };
    }
    
    return {
      source: 'none',
      result: {
        message: "No similar errors found in memory",
      },
    };
  }

  // 5-4. 가이던스 종합
  private synthesizeGuidance(
    episodes: Episode[],
    bugPatterns: BugPatternMatch[],
    projectKnowledge: ProjectKnowledge | undefined,
    userPrefs: UserPreferences,
    task: Task
  ): Guidance {
    const guidance: Guidance = {
      suggested_approach: '',
      things_to_try: [],
      things_to_avoid: [],
      expected_challenges: [],
      estimated_complexity: 'medium',
      confidence: 0.5,
    };
    
    // 성공한 에피소드에서 접근법 추출
    const successfulEpisodes = episodes.filter(e => e.outcome.status === 'success');
    if (successfulEpisodes.length > 0) {
      guidance.suggested_approach = successfulEpisodes[0].execution.plan_summary;
      guidance.things_to_try = successfulEpisodes
        .flatMap(e => e.extracted_knowledge.tips)
        .slice(0, 5);
      guidance.confidence += 0.2;
    }
    
    // 실패한 에피소드에서 피할 것 추출
    const failedEpisodes = episodes.filter(e => e.outcome.status === 'failure');
    guidance.things_to_avoid = failedEpisodes
      .flatMap(e => e.extracted_knowledge.gotchas)
      .slice(0, 5);
    
    // 버그 패턴에서 솔루션 추출
    if (bugPatterns.length > 0) {
      const bestPattern = bugPatterns[0];
      if (!guidance.suggested_approach) {
        guidance.suggested_approach = bestPattern.recommended_solution?.description || '';
      }
      guidance.expected_challenges = bestPattern.pattern.typical_context.common_causes;
      guidance.confidence += bestPattern.score * 0.3;
    }
    
    // 프로젝트 지식에서 주의사항 추가
    if (projectKnowledge) {
      guidance.things_to_avoid.push(...projectKnowledge.team_knowledge.avoid_patterns);
      
      // 복잡도 추정
      const affectedFiles = task.context?.files || [];
      const hotspotOverlap = affectedFiles.filter(
        f => projectKnowledge.hotspots.high_complexity.includes(f)
      ).length;
      
      if (hotspotOverlap > 0) {
        guidance.estimated_complexity = 'high';
        guidance.expected_challenges.push('Involves complex code areas');
      }
    }
    
    // 사용자 선호도 반영
    if (userPrefs.learned_patterns.frequently_rejected.length > 0) {
      guidance.things_to_avoid.push(
        ...userPrefs.learned_patterns.frequently_rejected.slice(0, 3)
      );
    }
    
    return guidance;
  }
}

6. Memory Persistence & Storage
typescriptinterface MemoryStorage {
  // 로컬 파일 시스템
  local: LocalStorage;
  
  // 벡터 DB (유사도 검색)
  vector: VectorDatabase;
  
  // 구조화된 데이터
  structured: StructuredDatabase;
}

class MemoryPersistence {
  private storage: MemoryStorage;

  // 6-1. 저장 스키마
  private schemas = {
    episodes: {
      table: 'episodes',
      indices: ['project_id', 'task_type', 'outcome_status', 'created_at'],
      vector_field: 'task_description_embedding',
    },
    bug_patterns: {
      table: 'bug_patterns',
      indices: ['error_types', 'last_seen'],
    },
    project_knowledge: {
      table: 'project_knowledge',
      indices: ['project_id'],
    },
  };

  // 6-2. 에피소드 저장
  async saveEpisode(episode: Episode): Promise<void> {
    // 구조화된 데이터 저장
    await this.storage.structured.upsert('episodes', episode.id, {
      ...episode,
      task_description_embedding: undefined,  // 벡터는 별도 저장
    });
    
    // 벡터 저장
    await this.storage.vector.upsert(
      'episode_embeddings',
      episode.id,
      episode.task.description_embedding
    );
  }

  // 6-3. 백업 & 복구
  async backup(): Promise<BackupResult> {
    const timestamp = new Date().toISOString();
    const backupPath = `backups/memory_${timestamp}`;
    
    // 전체 메모리 덤프
    const dump = {
      episodes: await this.storage.structured.getAll('episodes'),
      bug_patterns: await this.storage.structured.getAll('bug_patterns'),
      project_knowledge: await this.storage.structured.getAll('project_knowledge'),
      user_preferences: await this.storage.structured.get('user_preferences', 'default'),
    };
    
    await this.storage.local.write(backupPath, JSON.stringify(dump));
    
    return {
      path: backupPath,
      size: JSON.stringify(dump).length,
      records: {
        episodes: dump.episodes.length,
        bug_patterns: dump.bug_patterns.length,
        projects: dump.project_knowledge.length,
      },
    };
  }

  // 6-4. 메모리 정리 (오래된/불필요한 것 제거)
  async cleanup(config: CleanupConfig): Promise<CleanupResult> {
    const removed = {
      episodes: 0,
      patterns: 0,
    };
    
    // 오래된 에피소드 제거
    if (config.max_age_days) {
      const cutoff = new Date();
      cutoff.setDate(cutoff.getDate() - config.max_age_days);
      
      const oldEpisodes = await this.storage.structured.query('episodes', {
        where: { created_at: { lt: cutoff } },
      });
      
      // 유용성 낮은 것만 제거
      for (const episode of oldEpisodes) {
        if (episode.metadata.usefulness_score < 0.3 && 
            episode.metadata.retrieval_count < 2) {
          await this.storage.structured.delete('episodes', episode.id);
          await this.storage.vector.delete('episode_embeddings', episode.id);
          removed.episodes++;
        }
      }
    }
    
    // 사용되지 않는 패턴 제거
    if (config.min_usage_count) {
      const unusedPatterns = await this.storage.structured.query('bug_patterns', {
        where: { 
          'stats.occurrence_count': { lt: config.min_usage_count },
          'stats.last_seen': { lt: new Date(Date.now() - 90 * 24 * 60 * 60 * 1000) }
        },
      });
      
      for (const pattern of unusedPatterns) {
        await this.storage.structured.delete('bug_patterns', pattern.id);
        removed.patterns++;
      }
    }
    
    return removed;
  }
}

7. Memory-Aware Agent Integration
Agent가 Memory를 활용하는 방법.
typescriptclass MemoryAwareAgent {
  private memoryRetrieval: MemoryRetrievalSystem;
  private workingMemory: WorkingMemoryManager;

  // 7-1. 태스크 시작 시
  async startTask(task: Task): Promise<EnhancedTask> {
    // 관련 기억 로드
    const memories = await this.memoryRetrieval.loadRelevantMemories(task);
    
    // 태스크 컨텍스트 강화
    const enhancedTask: EnhancedTask = {
      ...task,
      
      // 메모리에서 얻은 가이던스
      guidance: memories.guidance,
      
      // 유사 사례
      similar_cases: memories.similar_episodes.map(e => ({
        description: e.task.description,
        approach: e.execution.plan_summary,
        outcome: e.outcome.status,
        key_learnings: e.extracted_knowledge,
      })),
      
      // 관련 패턴
      relevant_patterns: memories.bug_patterns.map(p => ({
        pattern: p.pattern.signature,
        solution: p.recommended_solution,
        confidence: p.score,
      })),
      
      // 프로젝트 컨텍스트
      project_context: {
        conventions: memories.project_knowledge?.conventions,
        hotspots: memories.project_knowledge?.hotspots,
        avoid: memories.project_knowledge?.team_knowledge.avoid_patterns,
      },
      
      // 사용자 선호도
      user_prefs: memories.user_preferences,
    };
    
    // Working memory 초기화
    this.workingMemory.initSession(enhancedTask);
    
    return enhancedTask;
  }

  // 7-2. 플래닝 시 메모리 활용
  async planWithMemory(task: EnhancedTask): Promise<Plan> {
    const planPrompt = this.buildPlanPrompt(task);
    
    // 가이던스 포함
    if (task.guidance.suggested_approach) {
      planPrompt.append(`
        Based on past experience, consider this approach:
        ${task.guidance.suggested_approach}
        
        Things that worked before:
        ${task.guidance.things_to_try.join('\n')}
        
        Things to avoid:
        ${task.guidance.things_to_avoid.join('\n')}
      `);
    }
    
    // 유사 사례 참조
    if (task.similar_cases.length > 0) {
      const successCase = task.similar_cases.find(c => c.outcome === 'success');
      if (successCase) {
        planPrompt.append(`
          A similar task was successfully completed before:
          Task: ${successCase.description}
          Approach: ${successCase.approach}
          Key insight: ${successCase.key_learnings.tips[0]}
        `);
      }
    }
    
    // 프로젝트 컨벤션 적용
    if (task.project_context.conventions) {
      planPrompt.append(`
        Follow project conventions:
        - Naming: ${task.project_context.conventions.naming}
        - Testing: ${task.project_context.conventions.testing_patterns}
      `);
    }
    
    return await this.planner.plan(planPrompt);
  }

  // 7-3. 에러 발생 시 메모리 쿼리
  async handleErrorWithMemory(error: ErrorInfo): Promise<ErrorHandlingStrategy> {
    // 메모리에서 유사 에러 검색
    const memoryResult = await this.memoryRetrieval.queryDuringExecution({
      type: 'similar_error',
      context: { error },
    });
    
    if (memoryResult.source === 'semantic_memory' && memoryResult.result.pattern) {
      return {
        strategy: 'use_known_pattern',
        pattern: memoryResult.result.pattern,
        solution: memoryResult.result.recommended_solution,
        confidence: memoryResult.result.confidence,
      };
    }
    
    if (memoryResult.source === 'episodic_memory' && memoryResult.result.episode) {
      return {
        strategy: 'follow_past_success',
        reference_episode: memoryResult.result.episode,
        approach: memoryResult.result.solution_used,
      };
    }
    
    if (memoryResult.source === 'working_memory') {
      return {
        strategy: 'try_different_approach',
        reason: 'Same error occurred earlier',
        previous_attempt: memoryResult.result.previous_attempt,
      };
    }
    
    return {
      strategy: 'explore',
      reason: 'No relevant memory found',
    };
  }

  // 7-4. 태스크 완료 시 메모리 업데이트
  async completeTask(result: TaskResult): Promise<void> {
    // Working memory consolidation
    const episodicRecord = await this.workingMemory.consolidate();
    
    // Episodic memory에 저장
    const episodeId = await this.memoryRetrieval.episodicMemory.store(episodicRecord);
    
    // Semantic memory 학습
    const episode = await this.memoryRetrieval.episodicMemory.get(episodeId);
    await this.memoryRetrieval.semanticMemory.learnFromEpisode(episode);
    
    // 피드백 대기 (비동기)
    this.awaitUserFeedback(episodeId);
  }
}

8. Memory 시스템 메트릭
typescriptinterface MemoryMetrics {
  // Storage
  total_episodes: number;
  total_patterns: number;
  storage_size_mb: number;
  
  // Retrieval
  avg_retrieval_time_ms: number;
  cache_hit_rate: number;
  
  // Effectiveness
  memory_assisted_success_rate: number;    // 메모리 활용 시 성공률
  pattern_match_accuracy: number;           // 패턴 매칭 정확도
  guidance_helpfulness: number;             // 가이던스 유용성
  
  // Learning
  new_patterns_learned: number;
  patterns_reinforced: number;
  patterns_deprecated: number;
  
  // Usage
  most_used_patterns: Array<{ pattern_id: string; usage_count: number }>;
  most_referenced_episodes: Array<{ episode_id: string; reference_count: number }>;
}