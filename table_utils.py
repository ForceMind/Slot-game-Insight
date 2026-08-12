from __future__ import annotations

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode


AG_GRID_LOCALE_ZH_CN = {
    "page": "页",
    "firstPage": "首页",
    "lastPage": "末页",
    "nextPage": "下一页",
    "previousPage": "上一页",
    "more": "更多",
    "to": "至",
    "of": "共",
    "next": "下一页",
    "last": "末页",
    "first": "首页",
    "previous": "上一页",
    "pageSizeSelectorLabel": "每页行数：",
    "ariaPageSizeSelectorLabel": "每页行数",
    "loadingOoo": "正在加载...",
    "selectAll": "全选",
    "searchOoo": "搜索...",
    "blanks": "空白",
    "filterOoo": "筛选...",
    "applyFilter": "应用筛选",
    "equals": "等于",
    "notEqual": "不等于",
    "lessThan": "小于",
    "greaterThan": "大于",
    "lessThanOrEqual": "小于或等于",
    "greaterThanOrEqual": "大于或等于",
    "inRange": "范围内",
    "contains": "包含",
    "notContains": "不包含",
    "startsWith": "开头是",
    "endsWith": "结尾是",
    "andCondition": "并且",
    "orCondition": "或者",
    "resetFilter": "重置",
    "clearFilter": "清除",
    "cancelFilter": "取消",
    "noRowsToShow": "没有数据",
    "pinColumn": "固定列",
    "pinLeft": "固定到左侧",
    "pinRight": "固定到右侧",
    "noPin": "取消固定",
    "autosizeThisColumn": "自动调整此列",
    "autosizeAllColumns": "自动调整所有列",
    "resetColumns": "重置列",
    "copy": "复制",
    "copyWithHeaders": "复制（含表头）",
    "paste": "粘贴",
    "export": "导出",
    "csvExport": "导出 CSV",
    "columns": "列",
    "filters": "筛选",
    "chooseColumns": "选择列",
    "columnFilter": "列筛选",
    "sortAscending": "升序排列",
    "sortDescending": "降序排列",
    "sortUnSort": "取消排序",
    "columnMenu": "列菜单",
    "hideColumn": "隐藏列",
    "ariaLabelColumnMenu": "列菜单",
    "ariaLabelColumnFilter": "列筛选",
    "ariaColumnsList": "列列表",
    "ariaFilterInput": "筛选输入框",
    "ariaFilterValue": "筛选值",
    "ariaFilteringOperator": "筛选条件",
    "ariaLabelSelectField": "选择字段",
    "ariaLabelContextMenu": "上下文菜单",
    "ariaLabelSubMenu": "子菜单",
}

NUMBER_FORMATTER = JsCode(
    """
    function(params) {
      if (params.value === null || params.value === undefined || params.value === '') return '';
      return Number(params.value).toLocaleString('zh-CN', {maximumFractionDigits: 2});
    }
    """
)


def localized_grid(
    frame: pd.DataFrame,
    *,
    key: str,
    height: int = 430,
    page_size: int = 20,
    percent_columns: tuple[str, ...] = (),
) -> None:
    display = frame.copy()
    for column in display.select_dtypes(include=["datetime", "datetimetz"]).columns:
        display[column] = display[column].dt.strftime("%Y-%m-%d %H:%M:%S")

    all_columns = list(display.columns)
    with st.popover("表格设置"):
        st.caption("列头菜单提供中文筛选；其余表格功能在这里统一设置。")
        sort_column = st.selectbox(
            "排序列", ["不排序", *all_columns], key=f"{key}-sort-column"
        )
        sort_direction = st.segmented_control(
            "排序方式",
            options=["升序", "降序"],
            default="升序",
            selection_mode="single",
            key=f"{key}-sort-direction",
        ) or "升序"
        visible_columns = st.multiselect(
            "显示列（取消选择即隐藏）",
            options=all_columns,
            default=all_columns,
            key=f"{key}-visible-columns",
        )
        pinned_columns = st.multiselect(
            "固定到左侧",
            options=visible_columns,
            default=[],
            placeholder="选择要固定的列",
            key=f"{key}-pinned-columns",
        )
        auto_width = st.checkbox(
            "自动调整列宽", value=False, key=f"{key}-auto-width"
        )
        number_format = st.selectbox(
            "数字格式",
            options=["自动", "整数", "两位小数"],
            key=f"{key}-number-format",
        )

    if visible_columns:
        display = display[visible_columns]
    if sort_column != "不排序" and sort_column in display.columns:
        display = display.sort_values(
            sort_column, ascending=sort_direction == "升序", kind="stable"
        )

    builder = GridOptionsBuilder.from_dataframe(display)
    builder.configure_default_column(
        sortable=True,
        filter=True,
        resizable=True,
        suppressHeaderMenuButton=False,
    )
    page_size_options = sorted({10, 20, 25, 50, page_size})
    builder.configure_pagination(enabled=True, paginationAutoPageSize=False, paginationPageSize=page_size)
    for column in display.select_dtypes(include="number").columns:
        if column in percent_columns:
            builder.configure_column(
                column,
                type=["numericColumn"],
                valueFormatter=JsCode(
                    "function(params) { return params.value == null ? '' : Number(params.value).toLocaleString('zh-CN', {maximumFractionDigits: 2}) + '%'; }"
                ),
            )
        elif number_format == "整数":
            builder.configure_column(
                column,
                type=["numericColumn"],
                valueFormatter=JsCode(
                    "function(params) { return params.value == null ? '' : Number(params.value).toLocaleString('zh-CN', {maximumFractionDigits: 0}); }"
                ),
            )
        elif number_format == "两位小数":
            builder.configure_column(
                column,
                type=["numericColumn"],
                valueFormatter=JsCode(
                    "function(params) { return params.value == null ? '' : Number(params.value).toLocaleString('zh-CN', {minimumFractionDigits: 2, maximumFractionDigits: 2}); }"
                ),
            )
        else:
            builder.configure_column(
                column,
                type=["numericColumn"],
                valueFormatter=NUMBER_FORMATTER,
                headerTooltip=column,
            )
    for column in pinned_columns:
        if column in display.columns:
            builder.configure_column(column, pinned="left", lockPinned=False)
    builder.configure_grid_options(
        localeText=AG_GRID_LOCALE_ZH_CN,
        paginationPageSizeSelector=page_size_options,
        animateRows=False,
        suppressMenuHide=False,
        enableCellTextSelection=True,
        ensureDomOrder=True,
    )
    AgGrid(
        display,
        gridOptions=builder.build(),
        height=height,
        fit_columns_on_grid_load=auto_width,
        allow_unsafe_jscode=True,
        enable_enterprise_modules=False,
        update_on=[],
        key=key,
        theme="streamlit",
    )
