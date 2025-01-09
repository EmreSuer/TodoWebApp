// Move these functions outside of DOMContentLoaded
function toggleDescription(event, taskId) {
    // Convert taskId to string if it isn't already
    taskId = String(taskId);

    // Stop propagation to prevent other handlers from firing
    event.stopPropagation();

    // Don't toggle if clicking within edit mode or task actions
    if (event.target.closest('.edit-mode') || event.target.closest('.task-actions')) {
        return;
    }

    // Don't toggle if clicking on select elements or buttons
    if (event.target.tagName === 'SELECT' || event.target.tagName === 'BUTTON') {
        return;
    }

    const taskItem = event.target.closest('.task-item');
    const description = taskItem.querySelector('.task-description');
    const expandIcon = taskItem.querySelector('.expand-icon');

    if (description.style.display === 'none') {
        description.style.display = 'block';
        expandIcon.textContent = '▲';
    } else {
        description.style.display = 'none';
        expandIcon.textContent = '▼';
    }
}

function toggleEditMode(event, taskId) {
    // Convert taskId to string if it isn't already
    taskId = String(taskId);

    event.preventDefault();
    event.stopPropagation();

    const taskItem = event.target.closest('.task-item');
    const viewMode = taskItem.querySelector('.view-mode');
    const editMode = taskItem.querySelector('.edit-mode');
    const description = taskItem.querySelector('.task-description');

    // Always hide description when entering edit mode
    if (description) {
        description.style.display = 'none';
        const expandIcon = taskItem.querySelector('.expand-icon');
        if (expandIcon) {
            expandIcon.textContent = '▼';
        }
    }

    viewMode.style.display = 'none';
    editMode.style.display = 'flex';

    // Add click handler to prevent description toggle
    editMode.onclick = function(e) {
        e.stopPropagation();
    };
}

function cancelTaskEdit(event, taskId) {
    // Convert taskId to string if it isn't already
    taskId = String(taskId);

    event.preventDefault();
    event.stopPropagation(); // Prevent task description from toggling
    const taskItem = event.target.closest('.task-item');
    const viewMode = taskItem.querySelector('.view-mode');
    const editMode = taskItem.querySelector('.edit-mode');

    editMode.style.display = 'none';
    viewMode.style.display = 'flex';
}

function saveTaskEdit(event, taskId) {
    taskId = String(taskId);

    event.preventDefault();
    event.stopPropagation();
    const taskItem = event.target.closest('.task-item');
    const editMode = taskItem.querySelector('.edit-mode');

    const newName = editMode.querySelector('.edit-task-name').value;
    const newCategory = editMode.querySelector('.edit-category').value;
    const newPriority = editMode.querySelector('.edit-priority').value;

    fetch(`/update_task/${taskId}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            name: newName,
            category_id: newCategory,
            priority: newPriority
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            // Update the view mode with new values
            const viewMode = taskItem.querySelector('.view-mode');
            viewMode.querySelector('.task-text').textContent = newName;

            // Update category label in the top row
            const viewModeTop = viewMode.querySelector('.view-mode-top');
            const categoryLabel = viewModeTop.querySelector('.category-label');

            if (data.category) {
                if (categoryLabel) {
                    categoryLabel.textContent = data.category.name;
                    categoryLabel.style.backgroundColor = data.category.color;
                    categoryLabel.style.color = getContrastColor(data.category.color);
                } else {
                    // Create new category label if it didn't exist
                    const newLabel = document.createElement('span');
                    newLabel.className = 'category-label';
                    newLabel.textContent = data.category.name;
                    newLabel.style.backgroundColor = data.category.color;
                    newLabel.style.color = getContrastColor(data.category.color);
                    viewModeTop.appendChild(newLabel);
                }
            } else if (categoryLabel) {
                categoryLabel.remove();
            }

            // Update priority badge in the bottom row
            const viewModeBottom = viewMode.querySelector('.view-mode-bottom');
            const priorityBadge = viewModeBottom.querySelector('.badge');
            priorityBadge.className = `badge badge-${newPriority.toLowerCase()}`;
            priorityBadge.textContent = newPriority;

            // Update task item category class
            const categoryClasses = Array.from(taskItem.classList)
                .filter(cls => cls.startsWith('category-'));
            categoryClasses.forEach(cls => taskItem.classList.remove(cls));

            if (data.category) {
                taskItem.classList.add(`category-${data.category.id}`);
            }

            // Switch back to view mode
            editMode.style.display = 'none';
            viewMode.style.display = 'flex';
        } else {
            console.error('Error updating task');
        }
    })
    .catch(error => console.error('Error:', error));
}

function getContrastColor(hexcolor) {
    // Remove the # if present
    hexcolor = hexcolor.replace('#', '');

    // Convert to RGB
    const r = parseInt(hexcolor.substr(0, 2), 16);
    const g = parseInt(hexcolor.substr(2, 2), 16);
    const b = parseInt(hexcolor.substr(4, 2), 16);

    // Calculate luminance using the WCAG formula
    const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;

    // Return white for dark colors, black for light colors
    return luminance > 0.5 ? '#000000' : '#ffffff';
}

function updateCategoryButtonColors() {
    const categoryButtons = document.querySelectorAll('.category-btn[style*="background-color"]');
    categoryButtons.forEach(button => {
        const bgColor = button.style.backgroundColor;
        // Convert RGB to Hex
        const hex = rgbToHex(bgColor);
        button.style.color = getContrastColor(hex);
    });
}

function rgbToHex(rgb) {
    // Extract RGB values using regex
    const rgbValues = rgb.match(/\d+/g);
    if (!rgbValues) return '#000000';

    // Convert to hex
    const r = parseInt(rgbValues[0]).toString(16).padStart(2, '0');
    const g = parseInt(rgbValues[1]).toString(16).padStart(2, '0');
    const b = parseInt(rgbValues[2]).toString(16).padStart(2, '0');

    return `#${r}${g}${b}`;
}

function updateCategoryLabelColors() {
    const categoryLabels = document.querySelectorAll('.category-label[style*="background-color"]');
    categoryLabels.forEach(label => {
        const bgColor = label.style.backgroundColor;
        // Convert RGB to Hex
        const hex = rgbToHex(bgColor);
        label.style.color = getContrastColor(hex);
    });
}

document.addEventListener('DOMContentLoaded', function() {
    const toggleBtns = document.querySelectorAll('[data-target]');
    const taskListSection = document.getElementById('task-list-section');

    // Function to switch sections
    function switchSection(targetId) {
        // Remove active class from all buttons
        toggleBtns.forEach(b => b.classList.remove('active'));

        // Add active class to the button with matching target
        const targetBtn = document.querySelector(`[data-target="${targetId}"]`);
        if (targetBtn) {
            targetBtn.classList.add('active');
        }

        // Hide all sections
        document.querySelectorAll('.toggle-section').forEach(section => {
            section.style.display = 'none';
            section.classList.remove('visible');
        });

        // Show selected section
        const targetSection = document.getElementById(targetId);
        if (targetSection) {
            targetSection.style.display = 'block';
            setTimeout(() => {
                targetSection.classList.add('visible');
            }, 10);
        }

        // Update URL hash without triggering scroll
        history.replaceState(null, null, `#${targetId}`);
    }

    // Check URL hash on page load
    const hash = window.location.hash.slice(1); // Remove the # symbol
    if (hash && document.getElementById(hash)) {
        // If there's a valid hash, switch to that section
        switchSection(hash);
    } else {
        // If no hash or invalid hash, show task list section by default
        taskListSection.style.display = 'block';
        setTimeout(() => {
            taskListSection.classList.add('visible');
        }, 10);
    }

    // Add click handlers to all toggle buttons/links
    toggleBtns.forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            const targetId = this.dataset.target;
            switchSection(targetId);
        });
    });

    // Prevent category filter clicks from hiding the task list section
    const categoryFilter = document.querySelector('.category-filter');
    if (categoryFilter) {
        categoryFilter.addEventListener('click', function(e) {
            if (!e.target.matches('[data-target]')) { // Only if the clicked element isn't a toggle button
                e.stopPropagation();
                // Ensure task list section stays visible when clicking category filters
                switchSection('task-list-section');
            }
        });
    }

    // Prevent description toggle when interacting with edit mode controls
    document.querySelectorAll('.edit-mode').forEach(editMode => {
        editMode.addEventListener('click', function(event) {
            event.stopPropagation();
        });

        // Add specific listeners for select elements
        editMode.querySelectorAll('select').forEach(select => {
            select.addEventListener('change', function(event) {
                event.stopPropagation();
            });
            select.addEventListener('click', function(event) {
                event.stopPropagation();
            });
        });
    });

    // Add this line to update category button colors on page load
    updateCategoryButtonColors();

    // Add color input change listener
    const colorInput = document.querySelector('input[type="color"]');
    if (colorInput) {
        colorInput.addEventListener('input', function(e) {
            const previewButton = document.querySelector('.category-btn.preview');
            if (previewButton) {
                previewButton.style.backgroundColor = e.target.value;
                previewButton.style.color = getContrastColor(e.target.value);
            }
        });
    }

    // Add these lines to update colors on page load
    updateCategoryButtonColors();
    updateCategoryLabelColors();

    const fileInput = document.querySelector('input[type="file"]');
    if (fileInput) {
        fileInput.addEventListener('change', function(e) {
            const fileName = e.target.files[0]?.name;
            const label = fileName || 'No file chosen';
            // You can add a span next to the input to show the filename if desired
        });
    }
});