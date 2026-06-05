(function () {
    var overlay = document.querySelector("[data-loading-overlay]");
    var bulkForm = document.querySelector("[data-bulk-form]");
    var confirmModal = document.querySelector("[data-confirm-modal]");
    var confirmMessage = document.querySelector("[data-confirm-message]");
    var confirmAccept = document.querySelector("[data-confirm-accept]");
    var confirmCancel = document.querySelector("[data-confirm-cancel]");
    var pendingForm = null;

    function showLoading(label) {
        if (!overlay) {
            return;
        }
        var text = overlay.querySelector("[data-loading-text]");
        if (text) {
            text.textContent = label || "در حال بارگذاری...";
        }
        document.body.classList.add("is-loading");
        overlay.removeAttribute("hidden");
    }

    function hideLoading() {
        if (!overlay) {
            return;
        }
        document.body.classList.remove("is-loading");
        overlay.setAttribute("hidden", "hidden");
    }

    function showConfirm(form) {
        if (!confirmModal || !confirmAccept || !confirmCancel) {
            return false;
        }
        pendingForm = form;
        if (confirmMessage) {
            confirmMessage.textContent = form.dataset.confirmSubmit || "این عملیات روی دیتابیس اعمال می‌شود. مطمئن هستید؟";
        }
        confirmModal.removeAttribute("hidden");
        document.body.classList.add("has-modal");
        confirmCancel.focus();
        return true;
    }

    function hideConfirm() {
        pendingForm = null;
        if (confirmModal) {
            confirmModal.setAttribute("hidden", "hidden");
        }
        document.body.classList.remove("has-modal");
    }

    function markSubmitting(form) {
        var button = form.querySelector("button[type='submit']");
        if (button) {
            button.dataset.originalText = button.textContent || "";
            button.textContent = button.dataset.loadingLabel || "در حال انجام...";
            button.disabled = true;
        }
        showLoading(form.dataset.loadingLabel || "در حال اعمال تغییرات...");
    }

    function fieldValue(field) {
        return field.value == null ? "" : String(field.value);
    }

    function rowHasChanges(row) {
        var fields = row.querySelectorAll(".cell-input:not([readonly]):not(:disabled)");
        for (var index = 0; index < fields.length; index += 1) {
            if (fieldValue(fields[index]) !== String(fields[index].dataset.original || "")) {
                return true;
            }
        }
        return false;
    }

    function refreshBulkState() {
        if (!bulkForm) {
            return;
        }
        var dirtyRows = bulkForm.querySelectorAll("tr.is-dirty").length;
        var selectedRows = bulkForm.querySelectorAll("[data-row-select]:checked").length;
        var dirtyCount = bulkForm.querySelector("[data-dirty-count]");
        var selectedCount = bulkForm.querySelector("[data-selected-count]");
        var action = bulkForm.querySelector("[data-bulk-action]");
        var submit = bulkForm.querySelector("[data-bulk-submit]");
        var bar = bulkForm.querySelector("[data-bulk-bar]");
        var actionValue = action ? action.value : "save_changes";

        if (dirtyCount) {
            dirtyCount.textContent = String(dirtyRows);
        }
        if (selectedCount) {
            selectedCount.textContent = String(selectedRows);
        }
        if (submit) {
            submit.disabled = actionValue === "delete_selected" ? selectedRows === 0 : dirtyRows === 0;
        }
        if (bar) {
            bar.classList.toggle("is-active", dirtyRows > 0 || selectedRows > 0);
        }
    }

    function syncRowDirtyState(row) {
        var changed = rowHasChanges(row);
        row.classList.toggle("is-dirty", changed);
        row.querySelectorAll(".cell-input").forEach(function (field) {
            field.classList.toggle("is-changed", fieldValue(field) !== String(field.dataset.original || ""));
        });
        refreshBulkState();
    }

    function prepareBulkForm() {
        if (!bulkForm) {
            return;
        }
        bulkForm.querySelectorAll("input[data-generated-bulk]").forEach(function (input) {
            input.remove();
        });
        bulkForm.querySelectorAll("tr.is-dirty").forEach(function (row) {
            var input = document.createElement("input");
            input.type = "hidden";
            input.name = "_dirty_rows";
            input.value = row.dataset.rowIndex || "";
            input.dataset.generatedBulk = "true";
            bulkForm.appendChild(input);
        });
    }

    function setupCreateTableBuilder() {
        var form = document.querySelector("[data-create-table-form]");
        if (!form) {
            return;
        }
        var builder = form.querySelector("[data-column-builder]");
        var addButton = form.querySelector("[data-add-column-row]");
        var specInput = form.querySelector("[data-columns-spec]");

        function rows() {
            return Array.prototype.slice.call(builder.querySelectorAll("[data-column-row]"));
        }

        function updateRemoveButtons() {
            var currentRows = rows();
            currentRows.forEach(function (row) {
                var removeButton = row.querySelector("[data-remove-column]");
                if (removeButton) {
                    removeButton.disabled = currentRows.length === 1;
                }
            });
        }

        if (addButton && builder) {
            addButton.addEventListener("click", function () {
                var firstRow = builder.querySelector("[data-column-row]");
                if (!firstRow) {
                    return;
                }
                var clone = firstRow.cloneNode(true);
                clone.querySelectorAll("input").forEach(function (input) {
                    if (input.type === "checkbox") {
                        input.checked = input.hasAttribute("data-column-nullable");
                    } else {
                        input.value = "";
                    }
                });
                builder.appendChild(clone);
                updateRemoveButtons();
            });
        }

        builder.addEventListener("click", function (event) {
            var button = event.target.closest("[data-remove-column]");
            if (!button || rows().length === 1) {
                return;
            }
            button.closest("[data-column-row]").remove();
            updateRemoveButtons();
        });

        form.addEventListener("submit", function (event) {
            var specs = rows().map(function (row) {
                var name = row.querySelector("[data-column-name]").value.trim();
                var type = row.querySelector("[data-column-type]").value;
                var nullable = row.querySelector("[data-column-nullable]").checked;
                var primary = row.querySelector("[data-column-primary]").checked;
                if (!name) {
                    return "";
                }
                return [name, type, nullable ? "nullable" : "notnull", primary ? "pk" : ""].filter(Boolean).join(":");
            }).filter(Boolean);
            if (!specs.length) {
                event.preventDefault();
                return;
            }
            specInput.value = specs.join("\n");
        });

        updateRemoveButtons();
    }

    setupCreateTableBuilder();

    if (bulkForm) {
        bulkForm.querySelectorAll(".cell-input").forEach(function (field) {
            field.addEventListener("input", function () {
                syncRowDirtyState(field.closest("tr"));
            });
            field.addEventListener("change", function () {
                syncRowDirtyState(field.closest("tr"));
            });
        });

        bulkForm.querySelectorAll("[data-row-select]").forEach(function (checkbox) {
            checkbox.addEventListener("change", refreshBulkState);
        });

        var selectAll = bulkForm.querySelector("[data-select-all]");
        if (selectAll) {
            selectAll.addEventListener("change", function () {
                bulkForm.querySelectorAll("[data-row-select]").forEach(function (checkbox) {
                    checkbox.checked = selectAll.checked;
                });
                refreshBulkState();
            });
        }

        var bulkAction = bulkForm.querySelector("[data-bulk-action]");
        if (bulkAction) {
            bulkAction.addEventListener("change", refreshBulkState);
        }

        refreshBulkState();
    }

    document.addEventListener("submit", function (event) {
        var form = event.target;
        if (!(form instanceof HTMLFormElement)) {
            return;
        }
        if (form === bulkForm) {
            prepareBulkForm();
        }
        if (form.dataset.confirmedSubmit === "true") {
            delete form.dataset.confirmedSubmit;
            markSubmitting(form);
            return;
        }
        if (form.hasAttribute("data-confirm-submit")) {
            event.preventDefault();
            if (!showConfirm(form)) {
                form.dataset.confirmedSubmit = "true";
                form.requestSubmit();
            }
            return;
        }
        markSubmitting(form);
    });

    if (confirmAccept) {
        confirmAccept.addEventListener("click", function () {
            var form = pendingForm;
            hideConfirm();
            if (!form) {
                return;
            }
            form.dataset.confirmedSubmit = "true";
            form.requestSubmit();
        });
    }

    if (confirmCancel) {
        confirmCancel.addEventListener("click", hideConfirm);
    }

    if (confirmModal) {
        confirmModal.addEventListener("click", function (event) {
            if (event.target === confirmModal) {
                hideConfirm();
            }
        });
    }

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && pendingForm) {
            hideConfirm();
        }
    });

    document.addEventListener("click", function (event) {
        var link = event.target.closest("a");
        if (!link || link.target || link.hasAttribute("download")) {
            return;
        }
        if (link.origin !== window.location.origin) {
            return;
        }
        if (link.getAttribute("href") && link.getAttribute("href").charAt(0) === "#") {
            return;
        }
        showLoading(link.dataset.loadingLabel || "در حال بارگذاری صفحه...");
    });

    window.addEventListener("pageshow", hideLoading);
})();
