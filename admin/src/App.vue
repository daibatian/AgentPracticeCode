<script setup lang="ts">
/**
 * 管理后台外壳：登录门 + 顶部导航 + 全局提示
 *
 * 具体页面放在 views/ 下（用户管理、操作日志），加新板块只要往导航里加一项。
 */
import { onMounted, ref } from "vue";
import { History, LogOut, ShieldAlert, ShieldCheck, Users } from "@lucide/vue";

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

  <div v-else class="h-full flex flex-col bg-slate-100">
    <!-- 顶栏：标题 + 导航 -->
    <header class="shrink-0 bg-white border-b border-slate-200">
      <div class="px-5 py-3 flex items-center gap-3">
        <div class="p-1.5 rounded-lg bg-slate-900 text-white">
          <ShieldCheck :size="18" />
        </div>
        <div class="min-w-0">
          <h1 class="text-sm font-semibold text-slate-800">AI 私厨 · 管理后台</h1>
          <p class="text-[11px] text-slate-400">管理端</p>
        </div>

        <nav class="flex items-center gap-1 ml-3 bg-slate-100 rounded-xl p-1">
          <button
            v-for="item in TABS"
            :key="item.key"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors"
            :class="
              tab === item.key
                ? 'bg-white text-slate-800 font-medium shadow-sm'
                : 'text-slate-500 hover:text-slate-700'
            "
            @click="tab = item.key"
          >
            <component :is="item.icon" :size="14" />
            <span>{{ item.label }}</span>
          </button>
        </nav>

        <span class="ml-auto text-xs text-slate-500 hidden sm:inline">
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

    <UsersView
      v-if="tab === 'users'"
      :admin-name="adminName"
      @notify="pushToast"
      @auth-expired="logout"
    />
    <LogsView v-else @notify="pushToast" @auth-expired="logout" />

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
