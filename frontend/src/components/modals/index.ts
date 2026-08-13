// 弹窗注册表: 名称 -> 组件。GenericModal 按 ui.modal.name 用 <component :is> 渲染。
// 新增弹窗: 在此登记名称(与 ui.openModal(name, props) 中的 name 一致), 组件置于本目录。
import type { Component } from 'vue'

import ConfirmModal from './ConfirmModal.vue'
import ImportDataModal from './ImportDataModal.vue'
import RestoreBackupModal from './RestoreBackupModal.vue'
import SyncModal from './SyncModal.vue'
import RenameTableModal from './RenameTableModal.vue'
import CopyTableModal from './CopyTableModal.vue'
import MaintainTableModal from './MaintainTableModal.vue'
import NewTableModal from './NewTableModal.vue'
import SchemaDiffModal from './SchemaDiffModal.vue'
import DbUsersModal from './DbUsersModal.vue'
import EditRowModal from './EditRowModal.vue'
import AddRowModal from './AddRowModal.vue'
import PasteInsertModal from './PasteInsertModal.vue'
import ColumnStatsModal from './ColumnStatsModal.vue'
import CellDetailModal from './CellDetailModal.vue'
import RedisKeyModal from './RedisKeyModal.vue'
import RedisTtlModal from './RedisTtlModal.vue'
import ERDiagramModal from './ERDiagramModal.vue'
import ResultChartModal from './ResultChartModal.vue'
import ExplainPlanModal from './ExplainPlanModal.vue'
import GenDataModal from './GenDataModal.vue'

export const modalRegistry: Record<string, Component> = {
  ConfirmModal,
  ImportDataModal,
  RestoreBackupModal,
  SyncModal,
  RenameTableModal,
  CopyTableModal,
  MaintainTableModal,
  NewTableModal,
  SchemaDiffModal,
  DbUsersModal,
  EditRowModal,
  AddRowModal,
  PasteInsertModal,
  ColumnStatsModal,
  CellDetailModal,
  RedisKeyModal,
  RedisTtlModal,
  ERDiagramModal,
  ResultChartModal,
  ExplainPlanModal,
  GenDataModal,
}
