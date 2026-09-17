<script setup lang="ts">
/**
 * 管理后台外壳：登录门 + 顶部导航 + 全局提示
 *
 * 具体页面放在 views/ 下（用户管理、操作日志），加新板块只要往导航里加一项。
 */
import { computed, onMounted, ref } from "vue";
import {
  ChevronLeft,
  ChevronRight,
  History,
  LogOut,
  ShieldAlert,
  ShieldCheck,
  Users,
} from "@lucide/vue";

import LoginView from "./components/LoginView.vue";
import {
  ApiError,
  clearAdminAuth,
  fetchUsers,
  getAdminName,
  getAdminToken,
  setAdminAuth,
} from "./lib/api";
import LogsView from "./views/LogsView.vue";
import UsersView from "./views/UsersView.vue";
import { loadNumber, saveValue } from "./lib/resize";

type Phase = "booting" | "login" | "forbidden" | "ready";
type Tab = "users" | "logs";

// 导航项放在普通常量里（不放响应式），避免组件对象被 Vue 代理后报警告
const TABS = [
  { key: "users" as const, label: "用户管理", icon: Users },
  { key: "logs" as const, label: "操作日志", icon: History },
];

const phase = ref<Phase>("booting");
const tab = ref<Tab>("users");
const adminName = ref(getAdminName());

// 侧边栏收起状态记在本地，收起时只留图标（用 title 提示）
const SIDEBAR_KEY = "chef_admin_sidebar_collapsed_v1";
const collapsed = ref(loadNumber(SIDEBAR_KEY) === 1);
const sidebarWidth = computed(() => (collapsed.value ? 64 : 208));
const currentTabLabel = computed(
  () => TABS.find((item) => item.key === tab.value)?.label ?? "",
);

function toggleSidebar() {
  collapsed.value = !collapsed.value;
  saveValue(SIDEBAR_KEY, collapsed.value ? 1 : 0);
}

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

/** 登录后先拿一次用户列表，用来确认这个账号确实是管理员 */
async function enterAdmin() {
  try {
    await fetchUsers({ page: 1, size: 1 });
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
  tab.value = "users";
  await enterAdmin();
}

function logout() {
  clearAdminAuth();
  phase.value = "login";
  tab.value = "users";
  toasts.value = [];
}
</script>

<template>
  <div
    v-if="phase === 'booting'"
    class="h-full flex items-center justify-center text-slate-400 text-sm bg-slate-100"
  >
    正在加载…
  </div>

  <LoginView v-else-if="phase === 'login'" @success="handleLoginSuccess" />

  <!-- 登录成功但不是管理员：给明确出口，避免让人以为页面坏了 -->
  <div
    v-else-if="phase === 'forbidden'"
    class="h-full flex items-center justify-center bg-slate-100 px-4"
  >
    <div
      class="max-w-sm w-full bg-white rounded-2xl shadow-xl border border-slate-200 p-7 text-center"
    >
      <div
        class="mx-auto w-12 h-12 rounded-full bg-amber-100 text-amber-600 flex items-center justify-center mb-4"
      >
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

  <div v-else class="h-full flex bg-slate-100">
    <!-- 左侧菜单栏（可收起） -->
    <aside
      class="shrink-0 bg-white border-r border-slate-200 flex flex-col overflow-hidden transition-[width] duration-200"
      :style="{ width: `${sidebarWidth}px` }"
    >
      <div class="h-14 shrink-0 flex items-center gap-2 px-4 border-b border-slate-200">
        <div class="p-1.5 rounded-lg bg-slate-900 text-white shrink-0">
          <ShieldCheck :size="18" />
        </div>
        <span
          v-if="!collapsed"
          class="text-sm font-semibold text-slate-800 whitespace-nowrap"
        >
          AI 私厨 · 后台
        </span>
        <button
          v-if="!collapsed"
          class="ml-auto p-1 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition"
          title="收起侧边栏"
          @click="toggleSidebar"
        >
          <ChevronLeft :size="16" />
        </button>
      </div>

      <!-- 菜单 -->
      <nav class="flex-1 p-2 space-y-1">
        <button
          v-for="item in TABS"
          :key="item.key"
          class="w-full flex items-center gap-2.5 py-2.5 rounded-xl text-sm transition-colors"
          :class="[
            tab === item.key
              ? 'bg-slate-900 text-white font-medium'
              : 'text-slate-600 hover:bg-slate-100',
            collapsed ? 'justify-center px-0' : 'px-3',
          ]"
          :title="collapsed ? item.label : undefined"
          @click="tab = item.key"
        >
          <component :is="item.icon" :size="17" class="shrink-0" />
          <span v-if="!collapsed" class="whitespace-nowrap">{{ item.label }}</span>
        </button>
      </nav>

      <!-- 底部：收起时是展开按钮，展开时是账号信息 -->
      <div class="shrink-0 border-t border-slate-200 p-2">
        <button
          v-if="collapsed"
          class="w-full flex items-center justify-center py-2.5 rounded-xl text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition"
          title="展开侧边栏"
          @click="toggleSidebar"
        >
          <ChevronRight :size="18" />
        </button>

        <div v-else class="flex items-center gap-2 px-1.5 py-1.5">
          <div
            class="w-7 h-7 rounded-full bg-slate-800 text-white text-xs flex items-center justify-center shrink-0"
          >
            {{ (adminName || "?").slice(0, 1).toUpperCase() }}
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-xs font-medium text-slate-700 truncate">
              {{ adminName || "未登录" }}
            </p>
            <p class="text-[10px] text-slate-400">管理员</p>
          </div>
          <button
            class="p-1.5 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 transition shrink-0"
            title="退出登录"
            @click="logout"
          >
            <LogOut :size="15" />
          </button>
        </div>
      </div>
    </aside>

    <!-- 右侧内容区 -->
    <main class="flex-1 min-w-0 flex flex-col">
      <header
        class="h-14 shrink-0 bg-white border-b border-slate-200 flex items-center gap-3 px-5"
      >
        <button
          v-if="collapsed"
          class="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition"
          title="展开侧边栏"
          @click="toggleSidebar"
        >
          <ChevronRight :size="18" />
        </button>
        <h1 class="text-sm font-semibold text-slate-800">{{ currentTabLabel }}</h1>
        <span class="ml-auto text-xs text-slate-400 hidden sm:inline">
          AI 私厨 · 管理后台
        </span>
      </header>

      <UsersView
        v-if="tab === 'users'"
        :admin-name="adminName"
        @notify="pushToast"
        @auth-expired="logout"
      />
      <LogsView v-else @notify="pushToast" @auth-expired="logout" />
    </main>

    <!-- 全局操作提示 -->
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
