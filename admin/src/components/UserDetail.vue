<script setup lang="ts">
/**
 * 用户详情抽屉：**只读**展示（资料、本周额度、口味偏好）
 *
 * 对用户的操作（改额度 / 改权限 / 强制下线 / 重置密码 / 删除）都放在列表的「操作」列里，
 * 这里不放按钮——看资料是看资料，动手是动手，避免看到就顺手点。
 */
import { computed, ref, watch } from "vue";
import { Loader2, X } from "@lucide/vue";

import { fetchUser } from "../lib/api";
import { formatDateTime, formatRelative, formatResetTime, formatTokens } from "../lib/format";
import { beginResize, loadNumber, saveValue } from "../lib/resize";
import type { UserDetail } from "../types";

const props = defineProps<{ userId: number }>();
const emit = defineEmits<{ (e: "close"): void }>();

const detail = ref<UserDetail | null>(null);
const loading = ref(true);
const error = ref("");

// 抽屉宽度可拖拽调整，记在本地
const DRAWER_WIDTH_KEY = "chef_admin_drawer_width_v1";
const DEFAULT_DRAWER_WIDTH = 448;
const MIN_DRAWER_WIDTH = 360;

const drawerWidth = ref(loadNumber(DRAWER_WIDTH_KEY) ?? DEFAULT_DRAWER_WIDTH);

function startDrawerResize(event: PointerEvent) {
  beginResize(event, drawerWidth.value, {
    min: MIN_DRAWER_WIDTH,
    // 最大不超过窗口（留点边距），免得拖到看不见遮罩
    max: () => Math.min(window.innerWidth - 32, 960),
    sign: -1, // 手柄在左边缘：往左拖是变宽
    onMove: (size) => {
      drawerWidth.value = size;
    },
    onEnd: () => saveValue(DRAWER_WIDTH_KEY, drawerWidth.value),
  });
}

function resetDrawerWidth() {
  drawerWidth.value = DEFAULT_DRAWER_WIDTH;
  saveValue(DRAWER_WIDTH_KEY, drawerWidth.value);
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    detail.value = await fetchUser(props.userId);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载失败";
  } finally {
    loading.value = false;
  }
}

watch(() => props.userId, load, { immediate: true });

const usedPercent = computed(() => {
  const info = detail.value;
  if (!info || info.effective_quota <= 0) return 0;
  return Math.min(
    Math.max(Math.round((info.used_this_week / info.effective_quota) * 100), 0),
    100,
  );
});

const remainingPercent = computed(() => 100 - usedPercent.value);

const barClass = computed(() => {
  if (remainingPercent.value <= 0) return "bg-red-500";
  if (remainingPercent.value <= 10) return "bg-red-400";
  if (remainingPercent.value <= 30) return "bg-amber-400";
  return "bg-slate-800";
});
</script>

<template>
  <div class="fixed inset-0 z-40 flex justify-end">
    <div class="flex-1 bg-slate-900/20" @click="emit('close')" />

    <aside
      class="relative max-w-full bg-white h-full shadow-2xl flex flex-col"
      :style="{ width: `${drawerWidth}px` }"
    >
      <!-- 左边缘的拖拽手柄（小屏隐藏，宽度按屏幕自适应） -->
      <span
        class="hidden md:block group/handle absolute left-0 top-0 h-full w-2 cursor-col-resize z-10"
        title="拖拽调整面板宽度，双击恢复默认"
        @pointerdown="startDrawerResize"
        @dblclick="resetDrawerWidth"
      >
        <span
          class="absolute inset-y-0 left-1/2 w-px bg-slate-200 group-hover/handle:bg-slate-400 transition-colors"
        />
      </span>

      <header class="shrink-0 px-5 py-4 border-b border-slate-200 flex items-start gap-3">
        <div class="flex-1 min-w-0">
          <h2 class="text-sm font-semibold text-slate-800 truncate">
            {{ detail?.display_name || detail?.username || "加载中…" }}
          </h2>
          <p class="text-[11px] text-slate-400">
            用户名 {{ detail?.username || "—" }} · ID {{ userId }}
          </p>
        </div>
        <button
          class="p-1 text-slate-400 hover:text-slate-600"
          aria-label="关闭"
          @click="emit('close')"
        >
          <X :size="18" />
        </button>
      </header>

      <div class="flex-1 overflow-y-auto px-5 py-4 space-y-5">
        <div v-if="loading" class="text-sm text-slate-400 flex items-center gap-2">
          <Loader2 :size="14" class="animate-spin" /> 加载中…
        </div>

        <p
          v-if="error"
          class="text-xs text-red-500 bg-red-50 border border-red-100 rounded-xl px-3 py-2"
        >
          {{ error }}
        </p>

        <template v-if="detail">
          <!-- 概览 -->
          <section class="grid grid-cols-2 gap-3 text-xs">
            <div class="rounded-xl bg-slate-50 px-3 py-2">
              <div class="text-slate-400">角色</div>
              <div class="mt-0.5 font-medium text-slate-700">
                {{ detail.is_admin ? "管理员" : "普通用户" }}
              </div>
            </div>
            <div class="rounded-xl bg-slate-50 px-3 py-2">
              <div class="text-slate-400">注册时间</div>
              <div class="mt-0.5 font-medium text-slate-700">
                {{ formatDateTime(detail.created_at) }}
              </div>
            </div>
            <div class="rounded-xl bg-slate-50 px-3 py-2">
              <div class="text-slate-400">会话 / 登录设备</div>
              <div class="mt-0.5 font-medium text-slate-700">
                {{ detail.threads }} / {{ detail.sessions }}
              </div>
            </div>
            <div class="rounded-xl bg-slate-50 px-3 py-2">
              <div class="text-slate-400">最后活跃</div>
              <div class="mt-0.5 font-medium text-slate-700">
                {{ formatRelative(detail.last_active) }}
              </div>
            </div>
          </section>

          <!-- 本周额度（只读；改额度在列表的「操作」列） -->
          <section class="rounded-2xl border border-slate-200 p-4">
            <div class="flex items-center justify-between">
              <h3 class="text-sm font-medium text-slate-700">本周额度</h3>
              <span class="text-[11px] text-slate-400">
                {{ formatResetTime(detail.week.resets_at) }}重置
              </span>
            </div>

            <div class="mt-3 h-2 rounded-full bg-slate-100 overflow-hidden">
              <div
                class="h-full rounded-full transition-all"
                :class="barClass"
                :style="{ width: `${usedPercent}%` }"
              />
            </div>

            <div class="mt-2 flex items-center justify-between text-xs">
              <span class="text-slate-500">
                已用 {{ formatTokens(detail.used_this_week) }} ·
                {{ detail.effective_quota > 0 ? formatTokens(detail.effective_quota) : "不限" }} ·
                {{ detail.requests_this_week }} 次
              </span>
              <span class="font-medium text-slate-700">
                剩余
                {{ detail.effective_quota > 0 ? formatTokens(detail.remaining ?? 0) : "不限" }}
              </span>
            </div>

            <p class="mt-2 text-[11px] text-slate-400">
              额度
              {{ detail.weekly_token_quota === null
                ? "未单独设置，用全局默认"
                : `单独设置为 ${detail.weekly_token_quota}` }}；
              需要调整请用列表右侧的「调整额度」。
            </p>
          </section>

          <!-- 口味偏好 -->
          <section class="rounded-2xl border border-slate-200 p-4">
            <h3 class="text-sm font-medium text-slate-700 mb-3">口味偏好</h3>
            <dl class="space-y-2 text-xs">
              <div class="flex gap-3">
                <dt class="w-16 shrink-0 text-slate-400">口味</dt>
                <dd class="text-slate-700">{{ detail.preferences.taste || "—" }}</dd>
              </div>
              <div class="flex gap-3">
                <dt class="w-16 shrink-0 text-slate-400">辣度</dt>
                <dd class="text-slate-700">{{ detail.preferences.spicy_level || "—" }}</dd>
              </div>
              <div class="flex gap-3">
                <dt class="w-16 shrink-0 text-slate-400">饮食目标</dt>
                <dd class="text-slate-700">{{ detail.preferences.diet_goal || "—" }}</dd>
              </div>
              <div class="flex gap-3">
                <dt class="w-16 shrink-0 text-slate-400">忌口</dt>
                <dd class="text-slate-700">{{ detail.preferences.avoid_ingredients || "—" }}</dd>
              </div>
              <div class="flex gap-3">
                <dt class="w-16 shrink-0 text-slate-400">偏好菜系</dt>
                <dd class="text-slate-700">
                  {{ detail.preferences.preferred_cuisines.length
                    ? detail.preferences.preferred_cuisines.join("、")
                    : "—" }}
                </dd>
              </div>
              <div class="flex gap-3">
                <dt class="w-16 shrink-0 text-slate-400">备注</dt>
                <dd class="text-slate-700">{{ detail.preferences.notes || "—" }}</dd>
              </div>
            </dl>
          </section>
        </template>
      </div>
    </aside>
  </div>
</template>
