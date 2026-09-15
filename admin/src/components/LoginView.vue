<script setup lang="ts">
/** 管理端登录页：只有管理员账号能进 */
import { ref } from "vue";
import { KeyRound, Loader2, ShieldCheck, UserRound } from "@lucide/vue";

import { adminLogin, ApiError, setAdminAuth } from "../lib/api";

const emit = defineEmits<{
  (e: "success", payload: { token: string; username: string }): void;
}>();

const username = ref("");
const password = ref("");
const error = ref("");
const loading = ref(false);

async function submit() {
  error.value = "";
  if (!username.value.trim() || !password.value) {
    error.value = "请填写用户名和密码";
    return;
  }

  loading.value = true;
  try {
    const result = await adminLogin(username.value.trim(), password.value);
    setAdminAuth(result.token, result.username);
    emit("success", result);
  } catch (err) {
    error.value =
      err instanceof ApiError ? err.message : "登录失败，请稍后重试";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div
    class="min-h-screen flex items-center justify-center bg-slate-100 px-4"
  >
    <div
      class="w-full max-w-sm bg-white rounded-2xl shadow-xl border border-slate-200 p-7"
    >
      <div class="flex items-center gap-3 mb-6">
        <div class="p-2 rounded-xl bg-slate-900 text-white">
          <ShieldCheck :size="20" />
        </div>
        <div>
          <h1 class="text-lg font-semibold text-slate-800">管理后台</h1>
          <p class="text-xs text-slate-400">AI 私厨 · 仅管理员可登录</p>
        </div>
      </div>

      <form class="space-y-4" @submit.prevent="submit">
        <label class="block">
          <span class="text-xs font-medium text-slate-600">用户名</span>
          <div class="mt-1 relative">
            <UserRound
              :size="16"
              class="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
            />
            <input
              v-model="username"
              type="text"
              autocomplete="username"
              placeholder="管理员用户名"
              class="w-full pl-9 pr-3 py-2.5 text-sm rounded-xl border border-slate-200 focus:border-slate-400 focus:ring-2 focus:ring-slate-100 outline-none transition"
            />
          </div>
        </label>

        <label class="block">
          <span class="text-xs font-medium text-slate-600">密码</span>
          <div class="mt-1 relative">
            <KeyRound
              :size="16"
              class="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
            />
            <input
              v-model="password"
              type="password"
              autocomplete="current-password"
              placeholder="密码"
              class="w-full pl-9 pr-3 py-2.5 text-sm rounded-xl border border-slate-200 focus:border-slate-400 focus:ring-2 focus:ring-slate-100 outline-none transition"
            />
          </div>
        </label>

        <p v-if="error" class="text-xs text-red-500">{{ error }}</p>

        <button
          type="submit"
          :disabled="loading"
          class="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 disabled:opacity-50 text-white text-sm font-medium transition"
        >
          <Loader2 v-if="loading" :size="16" class="animate-spin" />
          <span>{{ loading ? "登录中…" : "登录" }}</span>
        </button>
      </form>

      <p class="mt-5 text-[11px] leading-relaxed text-slate-400">
        用你的普通账号也能登录，但只有被设为管理员的账号才能进入后台。
        管理员名单由服务端 <code>.env</code> 的 <code>ADMIN_USERNAMES</code> 决定。
      </p>
    </div>
  </div>
</template>
