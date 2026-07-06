<template>
  <main class="workspace">
    <section class="hero-strip">
      <div>
        <p class="eyebrow">LangGraph · SSE · Human Checkpoint · Hybrid Memory</p>
        <h1>短剧创作控制台</h1>
        <p class="hero-copy">
          从创意简述到项目圣经、单集剧本、审查分流和分镜表，一条链路完成长篇短剧生产。
        </p>
      </div>
      <div class="hero-metrics">
        <div>
          <strong>{{ projects.length }}</strong>
          <span>项目</span>
        </div>
        <div>
          <strong>{{ indexerStatus?.queue_size ?? 0 }}</strong>
          <span>索引队列</span>
        </div>
        <div>
          <strong>{{ job?.progress ?? 0 }}%</strong>
          <span>当前进度</span>
        </div>
      </div>
    </section>

    <section class="layout-grid" :class="{ 'focus-mode': focusMode }">
      <aside class="panel composer-panel">
        <div class="panel-heading">
          <div>
            <span class="kicker">Create</span>
            <h2>创作输入</h2>
          </div>
          <button class="icon-button" title="运行创作流程" :disabled="loading" @click="createScript">
            <Play v-if="!loading" :size="19" />
            <LoaderCircle v-else class="spin" :size="19" />
          </button>
        </div>

        <label>
          创意简述
          <textarea v-model="form.user_brief" rows="6" placeholder="一句话写清主角、冲突、爽点和反转。" />
        </label>

        <div class="field-grid">
          <label class="span-2">
            项目库
            <select v-model="form.project_id">
              <option value="">新建项目</option>
              <option v-for="project in projects" :key="project.id" :value="project.id">
                {{ project.title }} · {{ project.versions?.length || 0 }} 版
              </option>
            </select>
          </label>
          <label class="span-2">
            全局模型
            <input v-model.trim="form.model" list="model-presets" placeholder="输入任意百炼兼容模型 ID" />
            <datalist id="model-presets">
              <option v-for="model in modelOptions" :key="model.name" :value="model.name">
                {{ model.label || model.name }}
              </option>
            </datalist>
            <span class="field-hint">没有 qwen3.6-plus 额度也可以直接填 flash、glm 或 deepseek 等模型。</span>
          </label>
          <label>
            平台
            <select v-model="form.platform">
              <option>抖音</option>
              <option>快手</option>
              <option>视频号</option>
              <option>小红书</option>
            </select>
          </label>
          <label>
            题材
            <input v-model="form.genre" />
          </label>
          <label>
            受众
            <input v-model="form.audience" />
          </label>
          <label>
            单集秒数
            <input v-model.number="form.target_duration_sec" type="number" min="30" max="300" />
          </label>
          <label>
            总集数
            <input v-model.number="form.episode_count" type="number" min="1" max="100" />
          </label>
          <label>
            生成第几集
            <input v-model.number="form.episode_number" type="number" min="1" max="100" />
          </label>
        </div>

        <details class="model-routing">
          <summary>Agent 模式与模型路由</summary>
          <div class="agent-config-list">
            <div v-for="agentName in configurableAgents" :key="agentName" class="agent-config-row">
              <strong>{{ agentName }}</strong>
              <select v-model="form.agent_modes[agentName]">
                <option v-for="mode in modeOptions" :key="agentName + mode.value" :value="mode.value">
                  {{ mode.label }}
                </option>
              </select>
              <input
                v-model.trim="form.agent_models[agentName]"
                list="model-presets"
                :disabled="form.agent_modes[agentName] === 'tool'"
                placeholder="留空使用全局模型"
              />
            </div>
          </div>
        </details>

        <label class="toggle-row">
          <input v-model="form.human_review_enabled" type="checkbox" />
          <span>大纲生成后暂停，允许人工修改再继续</span>
        </label>

        <div class="primary-actions">
          <button class="primary" :disabled="loading" @click="createScript">
            <Sparkles :size="18" />
            {{ loading ? '生成中...' : '生成剧本' }}
          </button>
          <button
            v-if="selectedProject"
            class="secondary"
            :disabled="loading"
            type="button"
            @click="continueNextEpisode"
          >
            继续第 {{ nextEpisodeNumber }} 集
          </button>
        </div>

        <p v-if="error" class="error">{{ error }}</p>
      </aside>

      <section class="main-column">
        <article v-if="job" class="panel status-panel">
          <div class="status-header">
            <div>
              <span class="kicker">Live Stream</span>
              <h2>{{ job.message || '任务运行中' }}</h2>
            </div>
            <strong>{{ job.progress }}%</strong>
          </div>
          <div class="progress-track">
            <div class="progress-bar" :style="{ width: `${job.progress}%` }"></div>
          </div>
          <div class="status-meta">
            <span>{{ job.status }}</span>
            <span v-if="job.current_agent">当前节点：{{ job.current_agent }}</span>
          </div>
          <div v-if="job.logs?.length" class="timeline">
            <div v-for="entry in job.logs.slice(-6)" :key="entry.time + entry.message">
              {{ entry.message }}
            </div>
          </div>
          <div v-if="streamText" class="stream-box">{{ streamText }}</div>
        </article>

        <article v-if="humanInterrupt" class="panel checkpoint-panel">
          <div class="panel-heading">
            <div>
              <span class="kicker">Checkpoint</span>
              <h2>人工干预断点</h2>
            </div>
          </div>
          <label>
            大纲 JSON
            <textarea v-model="humanDraft.episode_outline" rows="8" />
          </label>
          <label>
            剧本初稿 JSON
            <textarea v-model="humanDraft.draft_script" rows="10" />
          </label>
          <label>
            人工备注
            <textarea v-model="humanDraft.human_notes" rows="3" placeholder="告诉后续 Agent 你改了什么、想保留什么。" />
          </label>
          <button class="primary" type="button" :disabled="resuming" @click="resumeJob">
            {{ resuming ? '继续中...' : '应用修改并继续' }}
          </button>
        </article>

        <article v-if="!result && !job" class="empty-stage">
          <div class="empty-card">
            <Clapperboard :size="42" />
            <h2>准备开机</h2>
            <p>填好创意简述后开始生成。开启人工断点时，主笔编剧产出大纲后会停下来等你改。</p>
          </div>
        </article>

        <section v-if="result" class="result-stack">
          <article class="panel actions-panel">
            <button class="secondary" type="button" @click="saveCurrent(true)">
              <Save :size="16" />
              保存为新版本
            </button>
            <button class="secondary" type="button" @click="downloadExport('docx')">
              <FileDown :size="16" />
              Word
            </button>
            <button class="secondary" type="button" @click="downloadExport('pdf')">
              <FileText :size="16" />
              PDF
            </button>
            <button class="secondary focus-toggle" type="button" @click="toggleFocusMode">
              <Minimize2 v-if="focusMode" :size="16" />
              <Maximize2 v-else :size="16" />
              {{ focusMode ? '退出专注' : '⛶ 专注模式' }}
            </button>
          </article>

          <article v-if="result.workflow_error" class="panel alert-panel">
            <div class="panel-heading">
              <div>
                <span class="kicker">Review</span>
                <h2>流程未通过</h2>
              </div>
            </div>
            <p>{{ result.workflow_error }}</p>
            <ul>
              <li v-for="finding in result.review_findings" :key="finding.category + finding.target">
                <strong>{{ finding.severity }}</strong> · {{ finding.category }}：{{ finding.message }}
              </li>
            </ul>
          </article>

          <article v-if="result.llm_warnings?.length" class="panel warning-panel">
            <h2>模型调用提示</h2>
            <ul>
              <li v-for="warning in result.llm_warnings" :key="warning">{{ warning }}</li>
            </ul>
          </article>

          <article class="panel bible-panel">
            <div class="panel-heading">
              <div>
                <span class="kicker">Series Bible</span>
                <h2>项目圣经</h2>
              </div>
              <BookOpen :size="22" />
            </div>
            <h3>{{ result.project_bible?.logline }}</h3>
            <p>{{ result.project_bible?.theme }}</p>
            <div class="character-grid">
              <div v-for="role in result.project_bible?.characters" :key="role.name" class="character-card">
                <strong>{{ role.name }}</strong>
                <span>{{ role.role }}</span>
                <p>{{ role.profile }}</p>
              </div>
            </div>
          </article>

          <article class="panel script-panel">
            <div class="panel-heading">
              <div>
                <span class="kicker">Episode</span>
                <h2>单集剧本</h2>
              </div>
              <Clapperboard :size="22" />
            </div>
            <label>
              剧名
              <input v-model="result.final_script.title" />
            </label>
            <label>
              前三秒钩子
              <textarea v-model="result.final_script.hook_3s" rows="3" />
            </label>
            <div class="inline-actions">
              <button class="mini-button accent" type="button" :disabled="rewriting.hook" @click="rewriteHook">
                {{ rewriting.hook ? '优化中...' : '强化钩子' }}
              </button>
              <button class="mini-button" type="button" @click="shortenToTarget">压缩到目标时长</button>
            </div>

            <div v-for="(scene, sceneIndex) in result.final_script?.scenes" :key="scene.scene_no" class="scene-card">
              <div class="scene-toolbar">
                <strong>场景 {{ scene.scene_no }}</strong>
                <div>
                  <button class="mini-button" type="button" :disabled="rewriting.scene === sceneIndex" @click="rewriteScene(sceneIndex)">
                    {{ rewriting.scene === sceneIndex ? '优化中...' : '优化场景' }}
                  </button>
                  <button class="mini-button ghost" type="button" @click="removeScene(sceneIndex)">删除</button>
                </div>
              </div>
              <div class="field-grid">
                <label>
                  场景地点
                  <input v-model="scene.location" />
                </label>
                <label>
                  时长秒数
                  <input v-model.number="scene.duration_sec" type="number" min="1" />
                </label>
              </div>
              <label>
                画面动作
                <textarea v-model="scene.action" rows="3" />
              </label>
              <div class="dialogue-list">
                <div v-for="(line, lineIndex) in scene.dialogue" :key="lineIndex" class="dialogue-row">
                  <input v-model="line.speaker" placeholder="角色" />
                  <input v-model="line.line" placeholder="台词" />
                  <button
                    class="mini-button"
                    type="button"
                    :disabled="rewriting.dialogue === `${sceneIndex}-${lineIndex}`"
                    @click="rewriteDialogue(sceneIndex, lineIndex)"
                  >
                    {{ rewriting.dialogue === `${sceneIndex}-${lineIndex}` ? '润色中...' : '润色' }}
                  </button>
                  <button class="mini-button ghost" type="button" @click="removeDialogue(sceneIndex, lineIndex)">删</button>
                </div>
              </div>
              <button class="mini-button" type="button" @click="addDialogue(sceneIndex)">新增台词</button>
            </div>
            <button class="secondary add-scene" type="button" @click="addScene">新增场景</button>
          </article>

          <article class="panel shots-panel">
            <div class="panel-heading">
              <div>
                <span class="kicker">Storyboard</span>
                <h2>拍摄分镜</h2>
              </div>
              <Table2 :size="22" />
            </div>
            <div class="shot-table">
              <div class="shot-head">镜号</div>
              <div class="shot-head">场景</div>
              <div class="shot-head">画面</div>
              <div class="shot-head">台词</div>
              <template v-for="(shot, shotIndex) in result.shooting_script" :key="shotIndex">
                <input v-model="shot['镜号']" />
                <input v-model="shot['场景']" />
                <textarea v-model="shot['画面']" rows="2" />
                <textarea v-model="shot['台词']" rows="2" />
              </template>
            </div>
            <button class="secondary shot-action" type="button" @click="rebuildShotsFromScenes">
              根据场景重建分镜
            </button>
          </article>
        </section>
      </section>

      <aside class="side-column">
        <article class="panel flow-panel">
          <div class="panel-heading">
            <div>
              <span class="kicker">Workflow</span>
              <h2>六 Agent 链路</h2>
            </div>
            <Workflow :size="22" />
          </div>
          <div class="agent-flow">
            <div v-for="agent in agents" :key="agent.name" class="agent-card" :class="{ active: isActive(agent.name) }">
              <component :is="agent.icon" :size="19" />
              <div>
                <strong>{{ agent.name }}</strong>
                <span>{{ agent.desc }}</span>
              </div>
            </div>
          </div>
          <div class="routing-box">
            <div class="route fatal">FATAL · 打回世界观</div>
            <div class="route severe">SEVERE · 重写单集</div>
            <div class="route minor">MINOR · 改写复审</div>
            <div class="route pass">PASS · 分镜定稿</div>
          </div>
        </article>

        <article class="panel memory-panel">
          <div class="panel-heading">
            <div>
              <span class="kicker">Memory</span>
              <h2>长篇记忆</h2>
            </div>
            <DatabaseZap :size="22" />
          </div>
          <div class="storage-status">
            <span>Device: {{ capabilities?.storage?.embedding_configured_device || '-' }} -> {{ capabilities?.storage?.embedding_runtime_device || '-' }}</span>
            <span>存储：{{ capabilities?.storage?.backend || 'loading' }}</span>
            <span>Embedding：{{ capabilities?.storage?.embedding_provider || '-' }} / {{ capabilities?.storage?.embedding_model || '-' }}</span>
            <span>检索：{{ capabilities?.storage?.retrieval || 'hybrid' }}</span>
          </div>

          <div v-if="indexerStatus" class="indexer-card">
            <div class="indexer-top">
              <strong>BGE-M3 异步索引</strong>
              <span :class="{ live: indexerStatus.running }">{{ indexerStatus.running ? '运行中' : '未启动' }}</span>
            </div>
            <p class="indexer-device">Device: {{ indexerStatus.configured_device || '-' }} -> {{ indexerStatus.runtime_device || '-' }}</p>
            <div class="indexer-stats">
              <div><strong>{{ indexerStatus.queue_size }}</strong><span>队列</span></div>
              <div><strong>{{ chunkCount('pending') }}</strong><span>Pending</span></div>
              <div><strong>{{ chunkCount('indexed') }}</strong><span>Indexed</span></div>
              <div><strong>{{ chunkCount('failed') }}</strong><span>Failed</span></div>
            </div>
            <p v-if="indexerStatus.last_error" class="index-error">{{ indexerStatus.last_error }}</p>
            <button class="secondary compact" type="button" :disabled="enqueueing" @click="enqueuePending">
              {{ enqueueing ? '入队中...' : '重新入队 pending' }}
            </button>
          </div>

          <div v-if="capabilities?.memory_architecture" class="memory-layers">
            <div v-for="item in capabilities.memory_architecture" :key="item.layer" class="memory-layer">
              <strong>{{ memoryLayerLabel(item.layer) }}</strong>
              <p>{{ item.role }}</p>
            </div>
          </div>
        </article>

        <article v-if="capabilities" class="panel capability-panel">
          <div class="panel-heading">
            <div>
              <span class="kicker">Tools</span>
              <h2>工具能力</h2>
            </div>
          </div>
          <div class="capability-grid">
            <span v-for="tool in capabilities.function_tools" :key="tool.name" :title="tool.description">
              {{ tool.label || tool.name }}
            </span>
          </div>
        </article>

        <article v-if="projects.length" class="panel library-panel">
          <div class="panel-heading">
            <div>
              <span class="kicker">Library</span>
              <h2>项目库</h2>
            </div>
            <Library :size="22" />
          </div>
          <div v-for="project in projects" :key="project.id" class="library-row">
            <button class="library-item" type="button" @click="selectProject(project.id)">
              <strong>{{ project.title }}</strong>
              <span>{{ project.versions?.length || 0 }} 版 · {{ project.genre }}</span>
            </button>
            <button class="danger-icon" type="button" title="删除项目" @click.stop="deleteProject(project)">
              <Trash2 :size="16" />
            </button>
          </div>
        </article>

        <article v-if="selectedProject?.versions?.length" class="panel library-panel">
          <div class="panel-heading">
            <div>
              <span class="kicker">Versions</span>
              <h2>项目版本</h2>
            </div>
          </div>
          <div v-for="version in selectedProject.versions" :key="version.id" class="library-row">
            <button class="library-item" type="button" @click="loadProjectVersion(version.id)">
              <strong>第 {{ version.episode || version.version_no }} 集 · {{ version.title }}</strong>
              <span>v{{ version.version_no }}</span>
            </button>
            <button class="danger-icon" type="button" title="删除剧集版本" @click.stop="deleteVersion(version)">
              <Trash2 :size="16" />
            </button>
          </div>
        </article>

        <article v-if="savedItems.length" class="panel library-panel">
          <div class="panel-heading">
            <div>
              <span class="kicker">Local</span>
              <h2>本地记录</h2>
            </div>
          </div>
          <div v-for="item in savedItems" :key="item.id" class="library-row">
            <button class="library-item" type="button" @click="loadSaved(item.id)">
              <strong>{{ item.title }}</strong>
              <span>{{ item.createdAt }}</span>
            </button>
            <button class="danger-icon" type="button" title="删除本地记录" @click.stop="deleteSaved(item.id)">
              <Trash2 :size="16" />
            </button>
          </div>
        </article>
      </aside>
    </section>
  </main>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import {
  BookOpen,
  BrainCircuit,
  Clapperboard,
  ClipboardCheck,
  DatabaseZap,
  FileDown,
  FileText,
  Library,
  LoaderCircle,
  Maximize2,
  Minimize2,
  PenLine,
  Play,
  RefreshCcw,
  Save,
  Sparkles,
  Table2,
  Trash2,
  Workflow,
} from 'lucide-vue-next'

const agentNames = {
  planner: '统筹策划',
  world: '世界观构建',
  writer: '主笔编剧',
  reviewer: '综合质检',
  rewriter: '改写迭代',
  director: '分镜导演',
}

const form = reactive({
  project_id: '',
  user_brief: '',
  model: 'qwen3.6-flash',
  agent_models: {
    [agentNames.planner]: '',
    [agentNames.world]: '',
    [agentNames.writer]: '',
    [agentNames.reviewer]: 'deepseek-v4-flash',
    [agentNames.rewriter]: 'qwen3.6-flash',
    [agentNames.director]: '',
  },
  agent_modes: {
    [agentNames.planner]: 'hybrid',
    [agentNames.world]: 'model',
    [agentNames.writer]: 'model',
    [agentNames.reviewer]: 'hybrid',
    [agentNames.rewriter]: 'model',
    [agentNames.director]: 'tool',
  },
  platform: '抖音',
  genre: '',
  audience: '',
  episode_count: 12,
  episode_number: 1,
  target_duration_sec: 90,
  fast_mode: true,
  human_review_enabled: false,
})

const modelOptions = ref([
  { name: 'qwen3.6-flash', label: 'Qwen 3.6 Flash' },
  { name: 'qwen3.6-flash-2026-04-16', label: 'Qwen 3.6 Flash 2026-04-16' },
  { name: 'glm-5.1', label: 'GLM 5.1' },
  { name: 'qwen3.6-35b-a3b', label: 'Qwen 3.6 35B A3B' },
  { name: 'deepseek-v4-flash', label: 'DeepSeek V4 Flash' },
])
const modeOptions = ref([
  { value: 'tool', label: '工具模式' },
  { value: 'model', label: '模型模式' },
  { value: 'hybrid', label: '混合模式' },
])
const agents = [
  { name: agentNames.planner, desc: '需求澄清、题材与平台分析', icon: BrainCircuit },
  { name: agentNames.world, desc: '主线、人设、规则与项目圣经', icon: BookOpen },
  { name: agentNames.writer, desc: '单集初稿和前三秒钩子', icon: PenLine },
  { name: agentNames.reviewer, desc: '连贯性与合规双审', icon: ClipboardCheck },
  { name: agentNames.rewriter, desc: '局部润色与复审回路', icon: RefreshCcw },
  { name: agentNames.director, desc: '定稿后生成拍摄分镜', icon: Clapperboard },
]
const configurableAgents = agents.map((agent) => agent.name)
const savedModelConfig = loadModelConfig()
if (savedModelConfig.model) form.model = savedModelConfig.model
if (savedModelConfig.agent_models) Object.assign(form.agent_models, savedModelConfig.agent_models)
if (savedModelConfig.agent_modes) Object.assign(form.agent_modes, savedModelConfig.agent_modes)

const result = ref(null)
const loading = ref(false)
const error = ref('')
const focusMode = ref(false)
const capabilities = ref(null)
const indexerStatus = ref(null)
const job = ref(null)
const streamText = ref('')
const humanInterrupt = ref(null)
const humanDraft = reactive({ episode_outline: '', draft_script: '', human_notes: '' })
const resuming = ref(false)
const enqueueing = ref(false)
const rewriting = reactive({ hook: false, scene: null, dialogue: '' })
cleanupLegacyLocalState()
const savedItems = ref(loadSavedItems())
const projects = ref([])
let eventSource = null
let indexerTimer = null
const apiBase = ''

const traceNames = computed(() => result.value?.trace?.map((item) => item.agent) || [])
const isActive = (name) => traceNames.value.includes(name) || job.value?.current_agent === name
const selectedProject = computed(() => projects.value.find((project) => project.id === form.project_id))
const nextEpisodeNumber = computed(() => nextEpisodeFromProject(selectedProject.value))

watch(
  () => ({
    model: form.model,
    agent_models: { ...form.agent_models },
    agent_modes: { ...form.agent_modes },
  }),
  (config) => {
    localStorage.setItem('short_drama_model_config', JSON.stringify(config))
  },
  { deep: true },
)

onMounted(async () => {
  await Promise.all([fetchModels(), fetchCapabilities(), fetchProjects(), fetchIndexerStatus()])
  indexerTimer = window.setInterval(fetchIndexerStatus, 5000)
})

onBeforeUnmount(() => {
  cleanupStream()
  if (indexerTimer) window.clearInterval(indexerTimer)
})

function toggleFocusMode() {
  focusMode.value = !focusMode.value
}

function loadModelConfig() {
  try {
    return JSON.parse(localStorage.getItem('short_drama_model_config') || '{}')
  } catch {
    return {}
  }
}

async function createScript() {
  if (!form.user_brief.trim()) {
    error.value = '请先填写创意简述'
    return
  }
  loading.value = true
  error.value = ''
  result.value = null
  job.value = null
  streamText.value = ''
  humanInterrupt.value = null
  cleanupStream()
  try {
    if (form.project_id) {
      await refreshSelectedProjectEpisode()
    }
    const response = await fetch(`${apiBase}/api/scripts/jobs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    })
    if (!response.ok) {
      const payload = await response.json().catch(() => null)
      throw new Error(payload?.detail || `请求失败：${response.status}`)
    }
    job.value = await response.json()
    connectJobStream(job.value.job_id)
  } catch (err) {
    error.value = err.message || '生成失败'
    loading.value = false
  }
}

function connectJobStream(jobId) {
  cleanupStream()
  eventSource = new EventSource(`${apiBase}/api/scripts/jobs/${jobId}/events`)
  eventSource.addEventListener('job', (event) => {
    job.value = JSON.parse(event.data)
  })
  eventSource.addEventListener('token', (event) => {
    const payload = JSON.parse(event.data)
    streamText.value += payload.text
  })
  eventSource.addEventListener('interrupt', (event) => {
    humanInterrupt.value = JSON.parse(event.data)
    humanDraft.episode_outline = JSON.stringify(humanInterrupt.value.episode_outline || {}, null, 2)
    humanDraft.draft_script = JSON.stringify(humanInterrupt.value.draft_script || {}, null, 2)
    humanDraft.human_notes = ''
    loading.value = false
  })
  eventSource.addEventListener('result', async (event) => {
    result.value = normalizeResult(JSON.parse(event.data))
    if (result.value.saved_project_id) form.project_id = result.value.saved_project_id
    await fetchProjects()
    await fetchIndexerStatus()
    form.episode_number = nextEpisodeNumber.value
    loading.value = false
    humanInterrupt.value = null
    cleanupStream()
  })
  eventSource.addEventListener('error', async (event) => {
    if (result.value || job.value?.status === 'succeeded') {
      cleanupStream()
      return
    }
    if (!event.data) {
      await reconcileJobAfterStreamError()
      cleanupStream()
      return
    }
    try {
      const payload = JSON.parse(event.data)
      error.value = payload.error || '生成流失败'
    } catch {
      return
    }
    loading.value = false
    cleanupStream()
  })
}

async function reconcileJobAfterStreamError() {
  const jobId = job.value?.job_id
  if (!jobId) {
    loading.value = false
    return
  }
  const response = await fetch(`${apiBase}/api/scripts/jobs/${jobId}`).catch(() => null)
  if (!response?.ok) {
    error.value = '生成流连接中断，请稍后查看任务结果'
    loading.value = false
    return
  }
  const latest = await response.json()
  job.value = latest
  if (latest.status === 'succeeded' && latest.result) {
    result.value = normalizeResult(latest.result)
    if (result.value.saved_project_id) form.project_id = result.value.saved_project_id
    await fetchProjects()
    await fetchIndexerStatus()
    form.episode_number = nextEpisodeNumber.value
    loading.value = false
    return
  }
  if (latest.status === 'failed') {
    error.value = latest.error || '生成失败'
    loading.value = false
    return
  }
  error.value = '生成流连接中断，任务仍在后台运行'
  loading.value = false
}

function cleanupStream() {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
}

async function resumeJob() {
  if (!job.value?.job_id) return
  resuming.value = true
  error.value = ''
  try {
    const payload = {
      episode_outline: JSON.parse(humanDraft.episode_outline || '{}'),
      draft_script: JSON.parse(humanDraft.draft_script || '{}'),
      human_notes: humanDraft.human_notes,
    }
    const response = await fetch(`${apiBase}/api/scripts/jobs/${job.value.job_id}/resume`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!response.ok) {
      const body = await response.json().catch(() => null)
      throw new Error(body?.detail || `继续失败：${response.status}`)
    }
    job.value = await response.json()
    humanInterrupt.value = null
    loading.value = true
    connectJobStream(job.value.job_id)
  } catch (err) {
    error.value = err.message || '继续失败'
  } finally {
    resuming.value = false
  }
}

async function fetchModels() {
  const response = await fetch(`${apiBase}/api/models`).catch(() => null)
  if (!response?.ok) return
  const payload = await response.json()
  if (payload?.models?.length) modelOptions.value = payload.models
  if (!form.model) form.model = payload.default || 'qwen3.6-flash'
  if (payload.agent_defaults) {
    for (const [agentName, config] of Object.entries(payload.agent_defaults)) {
      if (form.agent_modes[agentName] === undefined) form.agent_modes[agentName] = config.mode || 'model'
      if (form.agent_models[agentName] === undefined) form.agent_models[agentName] = config.model ?? ''
    }
  }
}

async function fetchCapabilities() {
  const response = await fetch(`${apiBase}/api/capabilities`).catch(() => null)
  if (!response?.ok) return
  const payload = await response.json()
  capabilities.value = payload
  indexerStatus.value = payload.memory_indexer || indexerStatus.value
  if (payload?.agent_modes?.length) modeOptions.value = payload.agent_modes
}

async function fetchIndexerStatus() {
  const response = await fetch(`${apiBase}/api/memory/indexer`).catch(() => null)
  if (!response?.ok) return
  indexerStatus.value = await response.json()
}

async function enqueuePending() {
  enqueueing.value = true
  try {
    const response = await fetch(`${apiBase}/api/memory/indexer/enqueue-pending`, { method: 'POST' })
    if (response.ok) {
      const payload = await response.json()
      indexerStatus.value = payload.status
    }
  } finally {
    enqueueing.value = false
  }
}

async function fetchProjects() {
  const response = await fetch(`${apiBase}/api/projects`).catch(() => null)
  if (!response?.ok) return
  const payload = await response.json()
  projects.value = payload.projects || []
}

async function selectProject(projectId) {
  form.project_id = projectId
  const response = await fetch(`${apiBase}/api/projects/${projectId}`)
  if (!response.ok) return
  const project = await response.json()
  form.user_brief = project.brief || form.user_brief
  form.platform = project.platform || form.platform
  form.genre = project.genre || form.genre
  form.episode_number = nextEpisodeFromProject(project)
  const latest = project.versions?.[0]
  if (latest?.result) {
    result.value = normalizeResult(latest.result)
    applyResultModelConfig(result.value)
  }
}

function loadProjectVersion(versionId) {
  const version = selectedProject.value?.versions?.find((item) => item.id === versionId)
  if (version?.result) {
    result.value = normalizeResult(version.result)
    applyResultModelConfig(result.value)
  }
}

async function deleteProject(project) {
  if (!project?.id) return
  const ok = window.confirm(`删除项目「${project.title}」及其所有剧集版本？此操作不可恢复。`)
  if (!ok) return
  const response = await fetch(`${apiBase}/api/projects/${project.id}`, { method: 'DELETE' })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    error.value = payload?.detail || `删除项目失败：${response.status}`
    return
  }
  removeSavedItems((item) => localProjectId(item) === project.id)
  if (form.project_id === project.id) {
    form.project_id = ''
    result.value = null
    form.episode_number = 1
  }
  await fetchProjects()
}

async function deleteVersion(version) {
  if (!selectedProject.value?.id || !version?.id) return
  const ok = window.confirm(`删除「第 ${version.episode || version.version_no} 集 · ${version.title}」？此操作不可恢复。`)
  if (!ok) return
  const response = await fetch(
    `${apiBase}/api/projects/${selectedProject.value.id}/versions/${version.id}`,
    { method: 'DELETE' },
  )
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    error.value = payload?.detail || `删除剧集失败：${response.status}`
    return
  }
  const projectId = selectedProject.value.id
  removeSavedItems(
    (item) =>
      localVersionId(item) === version.id ||
      (localProjectId(item) === projectId && localEpisode(item) === (version.episode || version.version_no)),
  )
  await fetchProjects()
  const project = projects.value.find((item) => item.id === projectId)
  if (!project) {
    form.project_id = ''
    result.value = null
    form.episode_number = 1
    return
  }
  form.project_id = project.id
  form.episode_number = nextEpisodeFromProject(project)
  const latest = project.versions?.[0]
  result.value = latest?.result ? normalizeResult(latest.result) : null
}

function continueNextEpisode() {
  if (!selectedProject.value) return
  form.project_id = selectedProject.value.id
  form.episode_number = nextEpisodeNumber.value
  createScript()
}

async function refreshSelectedProjectEpisode() {
  const response = await fetch(`${apiBase}/api/projects/${form.project_id}`).catch(() => null)
  if (!response?.ok) return
  const project = await response.json()
  const index = projects.value.findIndex((item) => item.id === project.id)
  if (index >= 0) projects.value[index] = project
  form.episode_number = nextEpisodeFromProject(project)
}

function nextEpisodeFromProject(project) {
  const versions = project?.versions || []
  const episodes = versions
    .map((version) => Number(version.episode || version.result?.episode_number || version.version_no || 0))
    .filter((number) => Number.isFinite(number) && number > 0)
  return episodes.length ? Math.max(...episodes) + 1 : 1
}

function addScene() {
  if (!result.value?.final_script) return
  const scenes = result.value.final_script.scenes || []
  scenes.push({
    scene_no: scenes.length + 1,
    location: '新场景',
    duration_sec: 30,
    action: '',
    dialogue: [{ speaker: '', line: '' }],
  })
  result.value.final_script.scenes = scenes
}

function removeScene(sceneIndex) {
  result.value.final_script.scenes.splice(sceneIndex, 1)
  result.value.final_script.scenes.forEach((scene, index) => {
    scene.scene_no = index + 1
  })
  rebuildShotsFromScenes()
}

function addDialogue(sceneIndex) {
  result.value.final_script.scenes[sceneIndex].dialogue.push({ speaker: '', line: '' })
}

function removeDialogue(sceneIndex, lineIndex) {
  result.value.final_script.scenes[sceneIndex].dialogue.splice(lineIndex, 1)
  rebuildShotsFromScenes()
}

function rebuildShotsFromScenes() {
  const scenes = result.value?.final_script?.scenes || []
  result.value.shooting_script = scenes.map((scene, index) => ({
    镜号: `${scene.scene_no || index + 1}-1`,
    场景: scene.location || '',
    画面: scene.action || '',
    台词: (scene.dialogue || []).map((line) => line.line).filter(Boolean).join(' / '),
    时长: `${scene.duration_sec || 0}s`,
    机位建议: '竖屏中近景，关键情绪切特写',
    表演重点: '压住节奏，在反转台词前留停顿',
  }))
}

async function callRewrite(endpoint, payload) {
  const response = await fetch(`${apiBase}/api/scripts/rewrite/${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      result: result.value,
      model: form.model,
      agent_models: form.agent_models,
      ...payload,
    }),
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail || `改写失败：${response.status}`)
  }
  const body = await response.json()
  if (body.warnings?.length) error.value = body.warnings.join('；')
  return body
}

async function rewriteHook() {
  if (!result.value?.final_script) return
  rewriting.hook = true
  error.value = ''
  try {
    const body = await callRewrite('hook', {
      hook_3s: result.value.final_script.hook_3s || '',
      instruction: '强化冲突、悬念和可拍摄性，控制在一句话或两句短句。',
    })
    result.value.final_script.hook_3s = body.hook_3s || result.value.final_script.hook_3s
  } catch (err) {
    error.value = err.message || '钩子优化失败'
  } finally {
    rewriting.hook = false
  }
}

async function rewriteScene(sceneIndex) {
  const scene = result.value?.final_script?.scenes?.[sceneIndex]
  if (!scene) return
  rewriting.scene = sceneIndex
  error.value = ''
  try {
    const body = await callRewrite('scene', {
      scene,
      instruction: '强化动作画面和节奏，台词更短更有冲突，保持原场景编号。',
    })
    result.value.final_script.scenes[sceneIndex] = body.scene || scene
    rebuildShotsFromScenes()
  } catch (err) {
    error.value = err.message || '场景优化失败'
  } finally {
    rewriting.scene = null
  }
}

async function rewriteDialogue(sceneIndex, lineIndex) {
  const scene = result.value?.final_script?.scenes?.[sceneIndex]
  const dialogue = scene?.dialogue?.[lineIndex]
  if (!dialogue) return
  rewriting.dialogue = `${sceneIndex}-${lineIndex}`
  error.value = ''
  try {
    const body = await callRewrite('dialogue', {
      scene,
      dialogue,
      instruction: '保留意思，改得更像短剧爆点台词，短、狠、有情绪。',
    })
    scene.dialogue[lineIndex] = body.dialogue || dialogue
    rebuildShotsFromScenes()
  } catch (err) {
    error.value = err.message || '台词润色失败'
  } finally {
    rewriting.dialogue = ''
  }
}

function shortenToTarget() {
  const scenes = result.value?.final_script?.scenes || []
  const target = Number(form.target_duration_sec || 90)
  const total = scenes.reduce((sum, scene) => sum + Number(scene.duration_sec || 0), 0)
  if (!total || total <= target) return
  const ratio = target / total
  scenes.forEach((scene) => {
    scene.duration_sec = Math.max(5, Math.round(Number(scene.duration_sec || 0) * ratio))
    scene.action = trimText(scene.action, 96)
    scene.dialogue = (scene.dialogue || []).slice(0, 3).map((line) => ({
      ...line,
      line: trimText(line.line, 42),
    }))
  })
  rebuildShotsFromScenes()
}

function trimText(text, maxLength) {
  if (!text || text.length <= maxLength) return text || ''
  return `${text.slice(0, maxLength - 1)}…`
}

function cleanupLegacyLocalState() {
  const cleanupKey = 'short_drama_clean_start_v1'
  if (localStorage.getItem(cleanupKey)) return
  try {
    const items = JSON.parse(localStorage.getItem('short_drama_saved_results') || '[]')
    const next = Array.isArray(items) ? items.filter((item) => !isLegacyDemoRecord(item)) : []
    localStorage.setItem('short_drama_saved_results', JSON.stringify(next))
    localStorage.setItem(cleanupKey, 'done')
  } catch {
    localStorage.removeItem('short_drama_saved_results')
    localStorage.setItem(cleanupKey, 'done')
  }
}

function loadSavedItems() {
  try {
    return JSON.parse(localStorage.getItem('short_drama_saved_results') || '[]')
  } catch {
    return []
  }
}

function persistSavedItems(next) {
  savedItems.value = next
  localStorage.setItem('short_drama_saved_results', JSON.stringify(next))
}

function removeSavedItems(predicate) {
  const next = savedItems.value.filter((item) => !predicate(item))
  if (next.length !== savedItems.value.length) persistSavedItems(next)
}

async function saveCurrent(syncRemote = false) {
  if (!result.value) return
  result.value.model = form.model
  result.value.agent_models = { ...form.agent_models }
  result.value.agent_modes = { ...form.agent_modes }
  const current = {
    id: crypto.randomUUID(),
    title: result.value.final_script?.title || result.value.project_bible?.logline || '未命名剧本',
    createdAt: new Date().toLocaleString(),
    result: result.value,
  }
  const next = [current, ...savedItems.value].slice(0, 12)
  persistSavedItems(next)
  if (syncRemote) {
    const response = await fetch(`${apiBase}/api/projects/save-version`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: form.project_id || result.value.saved_project_id || result.value.project_id,
        title: current.title,
        result: result.value,
      }),
    })
    if (response.ok) {
      const payload = await response.json()
      form.project_id = payload.project.id
      result.value.saved_project_id = payload.project.id
      result.value.saved_version_id = payload.version.id
      await fetchProjects()
      await fetchIndexerStatus()
    }
  }
}

function loadSaved(id) {
  const item = savedItems.value.find((candidate) => candidate.id === id)
  if (item) {
    result.value = normalizeResult(item.result)
    applyResultModelConfig(result.value)
  }
}

function deleteSaved(id) {
  persistSavedItems(savedItems.value.filter((item) => item.id !== id))
}

function localProjectId(item) {
  return item?.result?.saved_project_id || item?.result?.project_id || ''
}

function localVersionId(item) {
  return item?.result?.saved_version_id || ''
}

function localEpisode(item) {
  return item?.result?.episode_number || item?.result?.final_script?.episode || null
}

function isLegacyDemoRecord(item) {
  const result = item?.result || {}
  const text = [
    item?.title,
    result?.user_brief,
    result?.final_script?.title,
    result?.project_bible?.logline,
  ]
    .filter(Boolean)
    .join(' ')
  return text.includes('订婚宴上的黑卡') || text.includes('黑卡') || text.includes('项目库测试')
}

async function downloadExport(format) {
  if (!result.value) return
  const response = await fetch(`${apiBase}/api/scripts/export/${format}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ result: result.value }),
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    error.value = payload?.detail || `导出失败：${response.status}`
    return
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = format === 'pdf' ? '短剧剧本.pdf' : '短剧剧本.docx'
  link.click()
  URL.revokeObjectURL(url)
}

function normalizeResult(payload) {
  if (!payload) return payload
  const next = payload
  next.final_script = next.final_script || {}
  next.final_script.scenes = next.final_script.scenes || []
  next.shooting_script = (next.shooting_script || []).map((shot) => ({
    镜号: shot['镜号'] ?? shot['闀滃彿'] ?? shot.shot_no ?? '',
    场景: shot['场景'] ?? shot['鍦烘櫙'] ?? shot.scene ?? '',
    画面: shot['画面'] ?? shot['鐢婚潰'] ?? shot.visual ?? '',
    台词: shot['台词'] ?? shot['鍙拌瘝'] ?? shot.dialogue ?? '',
    ...shot,
  }))
  return next
}

function applyResultModelConfig(payload) {
  if (!payload) return
  if (payload.model) form.model = payload.model
  if (payload.agent_models && typeof payload.agent_models === 'object') {
    Object.assign(form.agent_models, payload.agent_models)
  }
  if (payload.agent_modes && typeof payload.agent_modes === 'object') {
    Object.assign(form.agent_modes, payload.agent_modes)
  }
}

function chunkCount(status) {
  return indexerStatus.value?.chunk_counts?.[status] ?? 0
}

function memoryLayerLabel(layer) {
  const labels = {
    working_context: '工作上下文',
    series_state: '系列状态',
    episodic_memory: '剧集记忆',
    hybrid_retrieval: '混合检索',
    async_indexing: '异步索引',
  }
  return labels[layer] || layer
}
</script>
