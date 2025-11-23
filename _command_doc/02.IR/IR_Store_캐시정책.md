캐시 레이어

IRStore는 3단계 캐시 구조를 사용함

Layer 0: In-process LRU Cache

Layer 1: Redis Warm Cache

Layer 2: Kuzu / JSON Snapshot (Persistent)

단위

Hot/Cold 판단 단위는 개별 IRNode가 아니라 “파일 단위 FileIRBundle”임

FileIRBundle에는 해당 파일의 Node/Edge/Type/Signature/CFG 정보가 포함됨

Hotset 선정 기준

Hotset 후보 점수는 아래 요소의 가중합으로 산출함

최근 접근 빈도

워크스페이스에서 수정 여부 (변경 파일은 최우선 Hot)

LLM 쿼리에서의 등장 빈도

RepoMap/PageRank 등에서 계산된 중요도

주기적으로(score 기반) 상위 N개의 파일을 Hotset으로 유지하고, 나머지는 Cold로 내림

Eviction

In-process 캐시는 LRU + “워크스페이스 파일 핀 고정” 전략 사용

Redis는 maxmemory 범위 내에서 LRU로 자동 정리함

Cold 상태인 데이터는 언제든 Kuzu/JSON Snapshot에서 재로딩함

class IRStore:
    def get_file_ir(self, repo_id, snapshot_id, file_path) -> FileIRBundle:
        key = (repo_id, snapshot_id, file_path)

        # 1) in-process cache
        if key in self.file_cache:
            self._touch_access_log(key)
            return self.file_cache[key]

        # 2) Redis
        bundle = self.redis.get_file_bundle(key)
        if bundle is not None:
            self.file_cache.put(key, bundle)
            self._touch_access_log(key)
            return bundle

        # 3) Kuzu
        bundle = self.kuzu.load_file_bundle(key)
        self.redis.set_file_bundle(key, bundle)
        self.file_cache.put(key, bundle)
        self._touch_access_log(key)
        return bundle