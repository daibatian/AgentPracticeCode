<script setup lang="ts">
/** 操作日志：谁、什么时候、对谁、做了什么、结果如何 */
import { computed, onMounted, ref } from "vue";
import { Columns3, History, Loader2, RefreshCw } from "@lucide/vue";

import { ApiError, fetchLogs } from "../lib/api";
import { formatDateTime } from "../lib/format";
import { useColumns, type ColumnDef } from "../lib/useColumns";
import type { AdminLogRow } from "../types";

const emit = defineEmits<{
  (e: "notify", payload: { type: "ok" | "error"; text: string }): void;
  (e: "auth-expired"): void;
}>();

const COLUMNS: ColumnDef[] = [
  { key: "time", label: "时间", width: 160, min: 130, align: "left" },
  { key: "admin", label: "操作人", width: 130, min: 100, align: "left" },
  { key: "action", label: "操作", width: 120, min: 100, align: "left" },
  { key: "target", label: "对象", width: 150, min: 110, align: "left" },
  { key: "result", label: "结果", width: 90, min: 70, align: "left" },
  { key: "detail", label: "详情", width: 300, min: 160, align: "left" },
  { key: "ip", label: "IP", width: 130, min: 100, align: "left" },
];

const {
  widths: colWidths,
  boxRef: scrollBoxRef,
  totalWidth: tableWidth,
  startResize: startColumnResize,
  resetOne: resetColumn,
  resetAll: resetAllColumns,
} = useColumns("chef_admin_cols_logs_v1", COLUMNS);

const logs = ref<AdminLogRow[]>([]);
const total = ref(0);
const page = ref(1);
const size = ref(20);
const loading = ref(false);
const listError = ref("");

const filterAction = ref("");
const filterResult = ref("");

const pageCount = computed(() => Math.max(Math.ceil(total.value / size.value), 1));

const rangeText = computed(() => {
  if (total.value === 0) return "共 0 条记录";
  const start = (page.value - 1) * size.value + 1;
  const end = Math.min(page.value * size.value, total.value);
  return `第 ${start}-${end} 条 / 共 ${total.value} 条`;
});

const ACTION_OPTIONS = [
  { value: "", label: "全部操作" },
  { value: "update_user", label: "修改用户" },
  { value: "logout_all", label: "强制下线" },
  { value: "reset_password", label: "重置密码" },
  { value: "delete_user", label: "删除账号" },
];

const RESULT_OPTIONS = [
  { value: "", label: "全部结果" },
  { value: "ok", label: "成功" },
  { value: "denied", label: "被拒绝" },
];

const ACTION_LABELS: Record<string, string> = {
  update_user: "修改用户",
  logout_all: "强制下线",
  reset_password: "重置密码",
  delete_user: "删除账号",
};

const DETAIL_LABELS: Record<string, string> = {
  is_admin: "管理员",
  weekly_token_quota: "周额度",
  removed_sessions: "清除登录态",
  cleared_sessions: "清除登录态",
  threads: "连带会话",
};

function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action;
}

/** 把 detail 里的键值翻译成人话 */
function detailText(detail: Record<string, unknown> | null): string {
  if (!detail) return "—";
  return Object.entries(detail)
    .map(([key, value]) => {
      const label = DETAIL_LABELS[key] ?? key;
      if (key === "is_admin") return `${label} → ${value ? "是" : "否"}`;
      if (value === null) return `${label} → 恢复默认`;
      if (typeof value === "number") return `${label} ${value.toLocaleString("zh-CN")}`;
      return `${label} → ${String(value)}`;
    })
    .join("，");
}

async function refresh() {
  loading.value = true;
  listError.value = "";
  try {
    const data = await fetchLogs({
      page: page.value,
      size: size.value,
      action: filterAction.value,
      result: filterResult.value,
    });
    logs.value = data.items;
    total.value = data.total;
  } catch (err) {
    if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
      emit("auth-expired");
      return;
    }
    listError.value = err instanceof Error ? err.message : "加载失败";
  } finally {
    loading.value = false;
  }
}

onMounted(refresh);

function applyFilter() {
  page.value = 1;
  refresh();
}

function goPage(next: number) {
  if (next < 1 || next > pageCount.value) return;
  page.value = next;
  refresh();
}
</script>

<template>
  <div class="flex-1 min-h-0 flex flex-col">
    <!-- 工具栏 -->
    <div class="shrink-0 px-5 py-3 flex items-center gap-2 flex-wrap">
      <select
        v-model="filterAction"
        class="px-3 py-2 text-sm rounded-xl border border-slate-200 bg-white focus:border-slate-400 outline-none transition"
        @change="applyFilter"
      >
        <option v-for="option in ACTION_OPTIONS" :key="option.value" :value="option.value">
          {{ option.label }}
        </option>
      </select>

      <select
        v-model="filterResult"
        class="px-3 py-2 text-sm rounded-xl border border-slate-200 bg-white focus:border-slate-400 outline-none transition"
        @change="applyFilter"
      >
        <option v-for="option in RESULT_OPTIONS" :key="option.value" :value="option.value">
          {{ option.label }}
        </option>
      </select>

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
        title="把各列宽度恢复成默认并铺满整行"
        @click="resetAllColumns"
      >
        <Columns3 :size="14" />
        <span>重置列宽</span>
      </button>
    </div>

    <!-- 列表 -->
    <div class="flex-1 min-h-0 px-5 pb-4">
      <div class="h-full bg-white rounded-2xl border border-slate-200 overflow-hidden flex flex-col">
        <div
          v-if="listError"
          class="px-4 py-2 text-xs text-red-500 bg-red-50 border-b border-red-100"
        >
          {{ listError }}
        </div>

        <div ref="scrollBoxRef" class="flex-1 overflow-auto">
          <table
            class="w-full text-sm"
            :style="{ tableLayout: 'fixed', width: '100%', minWidth: `${tableWidth}px` }"
          >
            <colgroup>
              <col
                v-for="(column, index) in COLUMNS"
                :key="column.key"
                :style="{ width: `${colWidths[index]}px` }"
              />
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
              <tr v-for="log in logs" :key="log.id" class="border-t border-slate-100">
                <td class="px-4 py-2.5 text-slate-500 text-xs whitespace-nowrap">
                  {{ formatDateTime(log.created_at) }}
                </td>
                <td class="px-4 py-2.5 text-slate-700">{{ log.admin_username }}</td>
                <td class="px-4 py-2.5 text-slate-700">{{ actionLabel(log.action) }}</td>
                <td class="px-4 py-2.5 text-slate-700">
                  {{ log.target_username || "—" }}
                </td>
                <td class="px-4 py-2.5">
                  <span
                    class="text-[11px] px-2 py-0.5 rounded-full"
                    :class="
                      log.result === 'ok'
                        ? 'bg-emerald-50 text-emerald-700'
                        : 'bg-amber-50 text-amber-700'
                    "
                  >
                    {{ log.result === "ok" ? "成功" : "被拒绝" }}
                  </span>
                </td>
                <td class="px-4 py-2.5 text-xs text-slate-500">
                  <span class="line-clamp-2">{{ detailText(log.detail) }}</span>
                  <span v-if="log.message" class="block text-amber-600">{{ log.message }}</span>
                </td>
                <td class="px-4 py-2.5 text-xs text-slate-400">
                  {{ log.ip || "—" }}
                </td>
                <td aria-hidden="true" />
              </tr>
              <tr v-if="!loading && logs.length === 0">
                <td :colspan="COLUMNS.length + 1" class="px-4 py-10 text-center text-slate-400">
                  <History :size="22" class="mx-auto mb-2 opacity-50" />
                  还没有操作记录
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div
          class="shrink-0 border-t border-slate-100 px-4 py-2.5 flex items-center gap-3 text-xs text-slate-500"
        >
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
  </div>
</template>
