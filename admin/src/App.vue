<script setup lang="ts">
/** 管理后台主界面：登录门 + 用户列表 + 用户详情抽屉 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  Columns3,
  Loader2,
  LogOut,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Users,
} from "@lucide/vue";

import LoginView from "./components/LoginView.vue";
import UserActions from "./components/UserActions.vue";
import UserDetail from "./components/UserDetail.vue";
import {
  ApiError,
  clearAdminAuth,
  fetchUsers,
  getAdminName,
  getAdminToken,
  setAdminAuth,
} from "./lib/api";
import { formatDate, formatTokens } from "./lib/format";
import { beginResize, clearValue, loadNumberArray, saveValue } from "./lib/resize";
import type { AdminUserRow } from "./types";

type Phase = "booting" | "login" | "forbidden" | "ready";

/** 表格列定义：宽度可以拖拽调整（双击手柄或点工具栏按钮恢复默认） */
const COLUMNS = [
  { key: "id", label: "ID", width: 64, min: 48, align: "left" },
  { key: "user", label: "用户", width: 200, min: 130, align: "left" },
  { key: "role", label: "角色", width: 96, min: 76, align: "left" },
  { key: "threads", label: "会话", width: 80, min: 64, align: "right" },
  { key: "sessions", label: "设备", width: 80, min: 64, align: "right" },
  { key: "usage", label: "本周用量", width: 150, min: 110, align: "right" },
  { key: "quota", label: "剩余额度", width: 120, min: 90, align: "right" },
  { key: "created", label: "注册时间", width: 120, min: 100, align: "left" },
  { key: "actions", label: "操作", width: 170, min: 150, align: "right" },
] as const;

// 列宽有两种状态：
//   自动（默认）：按表格可用宽度分配，始终铺满整行、右侧不留白；
//   手动：你拖过之后，就固定成你拖的样子，窗口变化也不再自动改。
// 只有手动状态才写本地存储——自动状态每次按当前宽度重算，换屏幕尺寸也不会错。
// v2：旧版本点「重置列宽」时会把"默认宽度"也写进本地，新版会把这种数据误判成
// 手动模式，于是启动后不再自动铺满。换成新 key，并把旧 key 清掉。
const COL_WIDTH_KEY = "chef_admin_cols_users_v2";
const LEGACY_COL_WIDTH_KEY = "chef_admin_cols_users_v1";
clearValue(LEGACY_COL_WIDTH_KEY);

const DEFAULT_WIDTHS: number[] = COLUMNS.map((column) => column.width);

const savedWidths = loadNumberArray(COL_WIDTH_KEY, COLUMNS.length);
const manualColumns = ref(savedWidths !== null);
const colWidths = ref<number[]>(savedWidths ?? [...DEFAULT_WIDTHS]);

/** 表格的滚动容器，用来量可用宽度 */
const scrollBoxRef = ref<HTMLElement | null>(null);
let resizeObserver: ResizeObserver | null = null;

/** 自动模式：把默认比例按可用宽度放大，刚好铺满整行 */
function fitColumnsToWidth() {
  const box = scrollBoxRef.value;
  if (!box || manualColumns.value) return;

  const available = box.clientWidth;
  if (available < 200) return;

  const baseTotal = DEFAULT_WIDTHS.reduce((total, width) => total + width, 0);
  const scale = available / baseTotal;
  colWidths.value = COLUMNS.map((column) =>
    Math.max(Math.round(column.width * scale), column.min),
  );
}

// 表格要等登录完成才渲染，onMounted 时容器还不存在——所以必须监听 ref：
// 容器一出现就立刻铺满，并挂上 ResizeObserver 应对窗口尺寸变化
watch(scrollBoxRef, (box) => {
  resizeObserver?.disconnect();
  resizeObserver = null;
  if (!box) return;

  nextTick(fitColumnsToWidth);

  if (typeof ResizeObserver !== "undefined") {
    resizeObserver = new ResizeObserver(() => fitColumnsToWidth());
    resizeObserver.observe(box);
  }
});

onMounted(() => nextTick(fitColumnsToWidth));

onBeforeUnmount(() => resizeObserver?.disconnect());

/** 表格最小宽度 = 各列之和，保证列拖宽后是横向滚动而不是把列压扁 */
const tableWidth = computed(() =>
  colWidths.value.reduce((total, width) => total + width, 0),
);

function startColumnResize(event: PointerEvent, index: number) {
  // 一旦动手拖，就切到手动模式，不再自动按容器宽度分配
  manualColumns.value = true;
  beginResize(event, colWidths.value[index], {
    min: COLUMNS[index].min,
    max: 420,
    onMove: (size) => {
      const next = [...colWidths.value];
      next[index] = size;
      colWidths.value = next;
    },
    onEnd: () => saveValue(COL_WIDTH_KEY, colWidths.value),
  });
}

function resetColumn(index: number) {
  const next = [...colWidths.value];
  next[index] = COLUMNS[index].width;
  colWidths.value = next;
  saveValue(COL_WIDTH_KEY, next);
}

function resetAllColumns() {
  // 回到自动模式：清掉本地存的手动宽度，再按当前宽度重新铺满
  manualColumns.value = false;
  clearValue(COL_WIDTH_KEY);
  fitColumnsToWidth();
}

const phase = ref<Phase>("booting");
const adminName = ref(getAdminName());

const users = ref<AdminUserRow[]>([]);
const total = ref(0);
const page = ref(1);
const size = ref(20);
const query = ref("");
const searchInput = ref("");
const loading = ref(false);
const listError = ref("");

const selectedId = ref<number | null>(null);

// 操作结果提示（右上角小气泡，几秒后自动消失）
interface Toast {
  id: number;
  type: "ok" | "error";
  text: string;
}

const toasts = ref<Toast[]>([]);
let toastSeq = 0;

function pushToast(payload: { type: "ok" | "error"; text: string }) {
  const id = (toastSeq += 1);
  toasts.value = [...toasts.value, { id, ...payload }];
  window.setTimeout(() => {
    toasts.value = toasts.value.filter((toast) => toast.id !== id);
  }, 4000);
}

const pageCount = computed(() => Math.max(Math.ceil(total.value / size.value), 1));

async function loadUsers() {
  const data = await fetchUsers({ q: query.value, page: page.value, size: size.value });
  users.value = data.items;
  total.value = data.total;
}

/** 界面上的刷新：出错只提示，不踢回登录页 */
async function refresh() {
  loading.value = true;
  listError.value = "";
  try {
    await loadUsers();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      clearAdminAuth();
      phase.value = "login";
      return;
    }
    listError.value = err instanceof Error ? err.message : "加载失败";
  } finally {
    loading.value = false;
  }
}

/** 首屏 / 登录后：先拿一次列表，用来判断这个账号到底是不是管理员 */
async function enterAdmin() {
  try {
    await loadUsers();
    phase.value = "ready";
  } catch (err) {
    if (err instanceof ApiError && err.status === 403) {
      phase.value = "forbidden";
      return;
    }
    clearAdminAuth();
    phase.value = "login";
  }
}

onMounted(async () => {
  if (!getAdminToken()) {
    phase.value = "login";
    return;
  }
  await enterAdmin();
});

async function handleLoginSuccess(payload: { token: string; username: string }) {
  setAdminAuth(payload.token, payload.username);
  adminName.value = payload.username;
  await enterAdmin();
}

function logout() {
  clearAdminAuth();
  users.value = [];
  total.value = 0;
  selectedId.value = null;
  phase.value = "login";
}

function search() {
  query.value = searchInput.value.trim();
  page.value = 1;
  refresh();
}

function goPage(next: number) {
  if (next < 1 || next > pageCount.value) return;
  page.value = next;
  refresh();
}

const rangeText = computed(() => {
  if (total.value === 0) return "共 0 个用户";
  const start = (page.value - 1) * size.value + 1;
  const end = Math.min(page.value * size.value, total.value);
  return `第 ${start}-${end} 条 / 共 ${total.value} 个用户`;
});
</script>

<template>
  <div v-if="phase === 'booting'" class="h-full flex items-center justify-center text-slate-400 text-sm bg-slate-100">
    正在加载…
  </div>

  <LoginView v-else-if="phase === 'login'" @success="handleLoginSuccess" />

  <!-- 登录成功但不是管理员：给明确出口，避免让人以为页面坏了 -->
  <div v-else-if="phase === 'forbidden'" class="h-full flex items-center justify-center bg-slate-100 px-4">
    <div class="max-w-sm w-full bg-white rounded-2xl shadow-xl border border-slate-200 p-7 text-center">
      <div class="mx-auto w-12 h-12 rounded-full bg-amber-100 text-amber-600 flex items-center justify-center mb-4">
        <ShieldAlert :size="22" />
      </div>
      <h2 class="text-base font-semibold text-slate-800">这个账号不是管理员</h2>
      <p class="mt-2 text-xs text-slate-500 leading-relaxed">
        账号 <span class="font-medium text-slate-700">{{ adminName || "当前账号" }}</span> 可以登录，
        但没有后台权限。需要的话，请让管理员把它加进服务端 <code>.env</code> 的
        <code>ADMIN_USERNAMES</code>。
      </p>
      <button
        class="mt-5 w-full py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-sm font-medium transition"
        @click="logout"
      >
        换个账号登录
      </button>
    </div>
  </div>

  <div v-else class="h-full flex flex-col bg-slate-100">
    <!-- 顶栏 -->
    <header class="shrink-0 bg-white border-b border-slate-200">
      <div class="px-5 py-3 flex items-center gap-3">
        <div class="p-1.5 rounded-lg bg-slate-900 text-white">
          <ShieldCheck :size="18" />
        </div>
        <div class="flex-1 min-w-0">
          <h1 class="text-sm font-semibold text-slate-800">AI 私厨 · 管理后台</h1>
          <p class="text-[11px] text-slate-400">用户管理</p>
        </div>
        <span class="text-xs text-slate-500 hidden sm:inline">
          管理员：<span class="font-medium text-slate-700">{{ adminName }}</span>
        </span>
        <button
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-slate-500 hover:text-red-500 hover:bg-red-50 transition"
          @click="logout"
        >
          <LogOut :size="14" />
          <span>退出</span>
        </button>
      </div>
    </header>

    <!-- 工具栏 -->
    <div class="shrink-0 px-5 py-3 flex items-center gap-2 flex-wrap">
      <div class="relative">
        <Search :size="14" class="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          v-model="searchInput"
          type="text"
          placeholder="按用户名或昵称搜索"
          class="pl-8 pr-3 py-2 w-56 text-sm rounded-xl border border-slate-200 bg-white focus:border-slate-400 outline-none transition"
          @keyup.enter="search"
        />
      </div>
      <button
        class="px-3 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-sm transition"
        @click="search"
      >
        搜索
      </button>
      <button
        v-if="query"
        class="px-3 py-2 rounded-xl border border-slate-200 bg-white hover:border-slate-400 text-sm text-slate-600 transition"
        @click="searchInput = ''; search()"
      >
        清空
      </button>
      <button
        class="ml-auto flex items-center gap-1.5 px-3 py-2 rounded-xl border border-slate-200 bg-white hover:border-slate-400 text-sm text-slate-600 transition"
        :disabled="loading"
        @click="refresh"
      >
        <RefreshCw :size="14" :class="loading ? 'animate-spin' : ''" />
        <span>刷新</span>
      </button>
      <button
        class="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-slate-200 bg-white hover:border-slate-400 text-sm text-slate-600 transition"
        title="把各列宽度恢复成默认值"
        @click="resetAllColumns"
      >
        <Columns3 :size="14" />
        <span>重置列宽</span>
      </button>
    </div>

    <!-- 列表 -->
    <div class="flex-1 min-h-0 px-5 pb-4">
      <div class="h-full bg-white rounded-2xl border border-slate-200 overflow-hidden flex flex-col">
        <div v-if="listError" class="px-4 py-2 text-xs text-red-500 bg-red-50 border-b border-red-100">
          {{ listError }}
        </div>

        <div ref="scrollBoxRef" class="flex-1 overflow-auto">
          <table
            class="w-full text-sm"
            :style="{
              tableLayout: 'fixed',
              width: '100%',
              minWidth: `${tableWidth}px`,
            }"
          >
            <colgroup>
              <col
                v-for="(column, index) in COLUMNS"
                :key="column.key"
                :style="{ width: `${colWidths[index]}px` }"
              />
              <!-- 占位列：吃掉剩余宽度，这样真实列渲染出来就是设定的像素值，
                   拖某一列时其它列不会跟着变（否则浏览器会按比例缩放） -->
              <col />
            </colgroup>
            <thead class="bg-slate-50 text-slate-500 text-xs sticky top-0 z-10">
              <tr>
                <th
                  v-for="(column, index) in COLUMNS"
                  :key="column.key"
                  class="relative font-medium px-4 py-2.5 select-none"
                  :class="column.align === 'right' ? 'text-right' : 'text-left'"
                >
                  <span class="truncate">{{ column.label }}</span>
                  <!-- 拖拽手柄：视觉上是一条分隔线，命中区域放宽到 8px 更好抓 -->
                  <span
                    class="group/handle absolute right-0 top-0 h-full w-2 cursor-col-resize"
                    :title="`拖拽调整「${column.label}」列宽，双击恢复默认`"
                    @pointerdown="startColumnResize($event, index)"
                    @dblclick="resetColumn(index)"
                  >
                    <span
                      class="absolute inset-y-0 right-0 w-px bg-slate-200 group-hover/handle:bg-slate-400 transition-colors"
                    />
                  </span>
                </th>
                <th class="font-medium" aria-hidden="true" />
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="user in users"
                :key="user.id"
                class="border-t border-slate-100 hover:bg-slate-50 cursor-pointer transition"
                :class="selectedId === user.id ? 'bg-slate-50' : ''"
                @click="selectedId = user.id"
              >
                <td class="px-4 py-2.5 text-slate-400">{{ user.id }}</td>
                <td class="px-4 py-2.5">
                  <div class="font-medium text-slate-800">
                    {{ user.display_name || user.username }}
                  </div>
                  <div class="text-[11px] text-slate-400">{{ user.username }}</div>
                </td>
                <td class="px-4 py-2.5">
                  <span
                    class="text-[11px] px-2 py-0.5 rounded-full"
                    :class="user.is_admin
                      ? 'bg-slate-900 text-white'
                      : 'bg-slate-100 text-slate-500'"
                  >
                    {{ user.is_admin ? "管理员" : "用户" }}
                  </span>
                </td>
                <td class="px-4 py-2.5 text-right text-slate-600">{{ user.threads }}</td>
                <td class="px-4 py-2.5 text-right text-slate-600">{{ user.sessions }}</td>
                <td class="px-4 py-2.5 text-right text-slate-600">
                  {{ formatTokens(user.used_this_week) }}
                  <span class="text-[11px] text-slate-400">/ {{ user.requests_this_week }} 次</span>
                </td>
                <td class="px-4 py-2.5 text-right">
                  <span v-if="user.effective_quota <= 0" class="text-slate-400">不限</span>
                  <span v-else :class="(user.remaining ?? 0) <= 0 ? 'text-red-600' : 'text-slate-600'">
                    {{ formatTokens(user.remaining ?? 0) }}
                  </span>
                </td>
                <td class="px-4 py-2.5 text-slate-500 text-xs">
                  {{ formatDate(user.created_at) }}
                </td>
                <td class="px-2 py-1.5">
                  <!-- 所有对用户的操作都在这里；自己的账号会禁用敏感操作 -->
                  <UserActions
                    :user="user"
                    :self="user.username === adminName"
                    @changed="refresh"
                    @notify="pushToast"
                  />
                </td>
                <!-- 对应 colgroup 里的占位列 -->
                <td aria-hidden="true" />
              </tr>
              <tr v-if="!loading && users.length === 0">
                <td
                  :colspan="COLUMNS.length + 1"
                  class="px-4 py-10 text-center text-slate-400"
                >
                  <Users :size="22" class="mx-auto mb-2 opacity-50" />
                  {{ query ? "没有匹配的用户" : "还没有用户" }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="shrink-0 border-t border-slate-100 px-4 py-2.5 flex items-center gap-3 text-xs text-slate-500">
          <Loader2 v-if="loading" :size="14" class="animate-spin" />
          <span>{{ rangeText }}</span>
          <div class="ml-auto flex items-center gap-2">
            <button
              class="px-2.5 py-1 rounded-lg border border-slate-200 hover:border-slate-400 disabled:opacity-40 transition"
              :disabled="page <= 1"
              @click="goPage(page - 1)"
            >
              上一页
            </button>
            <span>{{ page }} / {{ pageCount }}</span>
            <button
              class="px-2.5 py-1 rounded-lg border border-slate-200 hover:border-slate-400 disabled:opacity-40 transition"
              :disabled="page >= pageCount"
              @click="goPage(page + 1)"
            >
              下一页
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 用户详情抽屉 -->
    <UserDetail
      v-if="selectedId !== null"
      :user-id="selectedId"
      @close="selectedId = null"
    />

    <!-- 操作结果提示 -->
    <div class="fixed top-4 right-4 z-[60] w-80 space-y-2">
      <div
        v-for="toast in toasts"
        :key="toast.id"
        class="rounded-xl border bg-white px-3.5 py-2.5 text-xs shadow-lg"
        :class="
          toast.type === 'ok'
            ? 'border-emerald-200 text-emerald-700'
            : 'border-red-200 text-red-600'
        "
      >
        {{ toast.text }}
      </div>
    </div>
  </div>
</template>
