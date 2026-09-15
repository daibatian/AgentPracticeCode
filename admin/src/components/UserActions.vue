<script setup lang="ts">
/**
 * 表格「操作」列：所有对用户的操作都收在这里，详情抽屉只负责展示
 *
 * 自己的账号会禁用敏感操作（改权限 / 强制下线 / 重置密码 / 删除），
 * 避免一键把自己踢下线或改掉自己的密码。
 */
import { computed, ref } from "vue";
import {
  BadgeCheck,
  Coins,
  KeyRound,
  Loader2,
  LogOut,
  ShieldOff,
  Trash2,
} from "@lucide/vue";

import ModalShell from "./ModalShell.vue";
import {
  ApiError,
  deleteUser,
  logoutAllSessions,
  patchUser,
  resetUserPassword,
} from "../lib/api";
import { formatTokens } from "../lib/format";
import type { AdminUserRow } from "../types";

const props = defineProps<{ user: AdminUserRow; self: boolean }>();
const emit = defineEmits<{
  (e: "changed"): void;
  (e: "notify", payload: { type: "ok" | "error"; text: string }): void;
}>();

type DialogKind = "" | "quota" | "reset" | "delete";

const busy = ref("");
const dialog = ref<DialogKind>("");
const quotaInput = ref("");
const quotaError = ref("");
const tempPassword = ref("");

const selfHint = computed(() => "不能对自己执行这个操作");

function ok(text: string) {
  emit("notify", { type: "ok", text });
}

function fail(err: unknown) {
  emit("notify", {
    type: "error",
    text:
      err instanceof ApiError || err instanceof Error
        ? err.message
        : "操作失败，请稍后重试",
  });
}

async function run(action: string, task: () => Promise<string>) {
  busy.value = action;
  try {
    ok(await task());
    emit("changed");
  } catch (err) {
    fail(err);
  } finally {
    busy.value = "";
  }
}

/* ---------------- 改权限 ---------------- */
function toggleAdmin() {
  if (props.self) return;
  const next = !props.user.is_admin;
  run("admin", async () => {
    await patchUser(props.user.id, { is_admin: next });
    return next
      ? `已把 ${props.user.username} 设为管理员`
      : `已取消 ${props.user.username} 的管理员权限`;
  });
}

/* ---------------- 强制下线 ---------------- */
function kickOut() {
  if (props.self) return;
  run("kick", async () => {
    const result = await logoutAllSessions(props.user.id);
    return `已把 ${props.user.username} 踢下线，清除 ${result.removed_sessions} 个登录令牌`;
  });
}

/* ---------------- 调整额度 ---------------- */
function openQuota() {
  quotaError.value = "";
  quotaInput.value =
    props.user.weekly_token_quota === null ? "" : String(props.user.weekly_token_quota);
  dialog.value = "quota";
}

async function saveQuota() {
  const raw = quotaInput.value.trim();
  let value: number | null = null;
  if (raw !== "") {
    const parsed = Number(raw);
    if (!Number.isInteger(parsed) || parsed < 0) {
      quotaError.value = "请填非负整数，或留空表示用全局默认额度";
      return;
    }
    value = parsed;
  }
  quotaError.value = "";
  await run("quota", async () => {
    await patchUser(props.user.id, { weekly_token_quota: value });
    return value === null
      ? `${props.user.username} 的额度已恢复为全局默认`
      : `${props.user.username} 的额度已设为 ${value} token/周`;
  });
  dialog.value = "";
}

/* ---------------- 重置密码 ---------------- */
function openReset() {
  if (props.self) return;
  tempPassword.value = "";
  dialog.value = "reset";
}

async function confirmReset() {
  await run("reset", async () => {
    const result = await resetUserPassword(props.user.id);
    tempPassword.value = result.password;
    return `${result.username} 的密码已重置`;
  });
}

async function copyPassword() {
  try {
    await navigator.clipboard.writeText(tempPassword.value);
    ok("临时密码已复制到剪贴板");
  } catch {
    ok("浏览器不允许自动复制，请手动选中复制");
  }
}

/* ---------------- 删除账号 ---------------- */
function openDelete() {
  if (props.self) return;
  dialog.value = "delete";
}

async function confirmDelete() {
  await run("delete", async () => {
    const result = await deleteUser(props.user.id);
    return `已删除 ${result.deleted.username}（连带 ${result.deleted.threads} 个会话）`;
  });
  dialog.value = "";
}
</script>

<template>
  <div class="flex items-center justify-end gap-0.5">
    <button
      class="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition"
      title="调整额度"
      @click.stop="openQuota"
    >
      <Coins :size="15" />
    </button>

    <button
      class="p-1.5 rounded-lg transition"
      :class="
        self
          ? 'text-slate-300 cursor-not-allowed'
          : 'text-slate-400 hover:text-slate-700 hover:bg-slate-100'
      "
      :title="self ? selfHint : user.is_admin ? '取消管理员权限' : '设为管理员'"
      :disabled="self || !!busy"
      @click.stop="toggleAdmin"
    >
      <ShieldOff v-if="user.is_admin" :size="15" />
      <BadgeCheck v-else :size="15" />
    </button>

    <button
      class="p-1.5 rounded-lg transition"
      :class="
        self
          ? 'text-slate-300 cursor-not-allowed'
          : 'text-slate-400 hover:text-slate-700 hover:bg-slate-100'
      "
      :title="self ? selfHint : '强制下线（清除他的登录态）'"
      :disabled="self || !!busy"
      @click.stop="kickOut"
    >
      <LogOut :size="15" />
    </button>

    <button
      class="p-1.5 rounded-lg transition"
      :class="
        self
          ? 'text-slate-300 cursor-not-allowed'
          : 'text-slate-400 hover:text-slate-700 hover:bg-slate-100'
      "
      :title="self ? selfHint : '重置密码'"
      :disabled="self || !!busy"
      @click.stop="openReset"
    >
      <KeyRound :size="15" />
    </button>

    <button
      class="p-1.5 rounded-lg transition"
      :class="
        self
          ? 'text-slate-300 cursor-not-allowed'
          : 'text-red-400 hover:text-red-600 hover:bg-red-50'
      "
      :title="self ? selfHint : '删除账号'"
      :disabled="self || !!busy"
      @click.stop="openDelete"
    >
      <Trash2 :size="15" />
    </button>

    <Loader2 v-if="busy" :size="14" class="animate-spin text-slate-400 ml-1" />
  </div>

  <!-- 调整额度 -->
  <ModalShell v-if="dialog === 'quota'" title="调整本周额度" @close="dialog = ''">
    <p class="text-xs text-slate-500 mb-3">
      用户 <span class="font-medium text-slate-700">{{ user.username }}</span>：
      当前{{ user.weekly_token_quota === null ? "未单独设置（用全局默认）" : `单独设置为 ${user.weekly_token_quota}` }}，
      本周已用 {{ formatTokens(user.used_this_week) }}。
    </p>
    <input
      v-model="quotaInput"
      type="text"
      inputmode="numeric"
      placeholder="留空 = 用全局默认额度，填 0 = 不限量"
      class="w-full px-3 py-2 text-sm rounded-xl border border-slate-200 focus:border-slate-400 outline-none transition"
      @keyup.enter="saveQuota"
    />
    <p v-if="quotaError" class="mt-2 text-xs text-red-500">{{ quotaError }}</p>
    <template #footer>
      <button
        class="px-3 py-2 rounded-xl border border-slate-200 text-sm text-slate-600 hover:border-slate-400 transition"
        @click="dialog = ''"
      >
        取消
      </button>
      <button
        class="px-3 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-sm transition disabled:opacity-50"
        :disabled="busy === 'quota'"
        @click="saveQuota"
      >
        {{ busy === "quota" ? "保存中…" : "保存" }}
      </button>
    </template>
  </ModalShell>

  <!-- 重置密码 -->
  <ModalShell v-if="dialog === 'reset'" title="重置密码" @close="dialog = ''">
    <template v-if="!tempPassword">
      <p class="text-sm text-slate-600 leading-relaxed">
        将给 <span class="font-medium text-slate-800">{{ user.username }}</span>
        生成一个新的临时密码，并把该用户所有登录令牌清掉（他需要用新密码重新登录）。
      </p>
      <p class="mt-2 text-xs text-amber-600">
        临时密码只显示这一次，请复制后发给对方。
      </p>
    </template>

    <template v-else>
      <p class="text-sm text-slate-600 mb-3">
        <span class="font-medium text-slate-800">{{ user.username }}</span> 的新临时密码：
      </p>
      <div class="flex items-center gap-2 rounded-xl bg-amber-50 border border-amber-200 px-3 py-2.5">
        <code class="flex-1 text-base font-mono text-amber-800">{{ tempPassword }}</code>
        <button
          class="px-2 py-1 rounded-lg text-xs text-amber-700 hover:bg-amber-100 transition"
          @click="copyPassword"
        >
          复制
        </button>
      </div>
      <p class="mt-2 text-xs text-slate-400">
        对方登录后可以在客户端的「个人中心 → 修改密码」里改成自己的密码。
      </p>
    </template>

    <template #footer>
      <template v-if="!tempPassword">
        <button
          class="px-3 py-2 rounded-xl border border-slate-200 text-sm text-slate-600 hover:border-slate-400 transition"
          @click="dialog = ''"
        >
          取消
        </button>
        <button
          class="px-3 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-sm transition disabled:opacity-50"
          :disabled="busy === 'reset'"
          @click="confirmReset"
        >
          {{ busy === "reset" ? "重置中…" : "确认重置" }}
        </button>
      </template>
      <button
        v-else
        class="px-3 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-sm transition"
        @click="dialog = ''"
      >
        我已记下
      </button>
    </template>
  </ModalShell>

  <!-- 删除账号 -->
  <ModalShell v-if="dialog === 'delete'" title="删除账号" @close="dialog = ''">
    <p class="text-sm text-slate-600 leading-relaxed">
      确定删除
      <span class="font-medium text-slate-800">{{ user.display_name || user.username }}</span>
      （{{ user.username }}）吗？
    </p>
    <p class="mt-2 text-sm text-red-600 leading-relaxed">
      会连带删除他的 {{ user.threads }} 个会话、全部对话记录、登录令牌和用量记录，
      <strong>不可恢复</strong>。
    </p>
    <template #footer>
      <button
        class="px-3 py-2 rounded-xl border border-slate-200 text-sm text-slate-600 hover:border-slate-400 transition"
        @click="dialog = ''"
      >
        取消
      </button>
      <button
        class="px-3 py-2 rounded-xl bg-red-600 hover:bg-red-700 text-white text-sm transition disabled:opacity-50"
        :disabled="busy === 'delete'"
        @click="confirmDelete"
      >
        {{ busy === "delete" ? "删除中…" : "确认删除" }}
      </button>
    </template>
  </ModalShell>
</template>
