function twoOptionDialog(message, option1, option1Callback, option2,
		option2Callback, element) {
	var options = {};
	options[option1] = function() {
		$(this).dialog("close");
		option1Callback();
	};
	options[option2] = function() {
		$(this).dialog("close");
		option2Callback();

	};
	$("<div></div>").dialog({
		autoOpen : true,
		title : message,
		modal : true,
		buttons : options
	});
}

function saveElementCopy(parentList) {
	// First element is a list divider, save the second
	var firstElem = $(parentList).children('li:first').next().clone(true, true);
	$(parentList).data('firstElem', firstElem);
}

//NOTE: To use this, you must have called saveElementCopy in 'pagebeforecreate' on the same list parent
// This is used by MultiInstanceVerticalComponentRenderer
function cloneListElement(element, maxInstances) {
	var elem = $(element).parent();
	var parent = elem.parent();
	elem.detach();
	cloneElementWithNewId(parent);

	// Move the button after the element we just added
	parent.append(elem);

	// Make any buttons visible
	enableButtons(parent, maxInstances);

	// Refresh the list view so styling is applied correctly
	parent.listview('refresh');
};

function cloneElementWithNewId(parentList) {
	// Clone an element and update its id so it remains unique
	var savedElem = $(parentList).data('firstElem');
	var elem = $(savedElem).clone(true,true);
	var instanceId=$(parentList).data('lastInstance');
	if (instanceId==null) {
		instanceId=0;
	}
	instanceId++;
	$(parentList).data('lastInstance',instanceId);
	updateId(elem, "-i"+instanceId);
	elem.appendTo($(parentList)).enhanceWithin();
	elem.trigger('create');		
}

function updateId(element, newSuffix) {
	// Recursive call to update the id of this element and all of its children to add the given suffix
	var elem = $(element);
	var currId = elem.prop('id');
	if (currId != null && currId != '') {
		elem.prop('id',currId+newSuffix);
		// Checkboxes, radio buttons and Select options should not lose their value 
		if (elem.prop('type') != 'checkbox' && elem.prop('type') != 'radio' && !elem.is('option')) {
			elem.val('');
		}
	}

	// label for='xxx'
	var forId = elem.prop('for');
	if (forId != null && forId != '') {
		elem.prop('for',forId+newSuffix).val('');
	}

	// Update the name as well to be unique
	var currName = elem.prop('name');
	if (currName !=null && currName != '') {
		elem.prop("name", currName+newSuffix);
	}

	if (elem.is('select')){
	   //remove event listeners from old dd and re apply
       elem.off('change', elem.data('handleDDChange'));
       elem.off('click', elem.data('handleDDClick'));
       elem.off('keydown', elem.data('handleDDKeydown'));
	   selfservice.dropdownfix(elem);
	}

	elem.children().each(function() {
		updateId($(this), newSuffix);
	});
}

function removeMyParentTree(element, maxInstances) {
	// The button is in a paragraph element in the list
	var parent = $(element).parents('.multi-vertical');
	var parentList = parent.parent();
	parent.remove();
	
	// Only one item left, don't allow it to be deleted
	// We have to add one extra item to account for the list divider
	enableButtons(parentList, maxInstances);
	parentList.listview();
	parentList.listview('refresh');
};

function enableButtons(parentList, maxInstances) {
	var children = parentList.children('li.multi-vertical');
	if (children.length <= 1) {
		parentList.find('a[data-icon="delete"]').hide();
		parentList.find('a[data-icon="arrow-u"]').hide();
		parentList.find('a[data-icon="arrow-d"]').hide();

	} else {
		parentList.find('a[data-icon="delete"]').show();

		var upButtons = parentList.find('a[data-icon="arrow-u"]');
		if (upButtons.length > 1) {
			$(upButtons[0]).hide();
			for (var i = 1; i < upButtons.length; i++) {
				$(upButtons[i]).show();
			}
		}

		var downButtons = parentList.find('a[data-icon="arrow-d"]');
		if (downButtons.length > 1) {
			$(downButtons[downButtons.length - 1]).hide();
			for (var i = 0; i < downButtons.length - 1; i++) {
				$(downButtons[i]).show();
			}
		}
	}

	if (maxInstances && maxInstances > 0) {
		var addButton = parentList.children().last().children('a');
		if (children.length >= maxInstances) {
			addButton.addClass('ui-disabled');
		} else {
			addButton.removeClass('ui-disabled');
		}
	}
//	console.log('refreshing list '+$(parentList).prop('id'));
};

function moveElement(button, down, maxInstances) {
	// The button is in a paragraph element in the list
	var element = $(button).parents('.multi-vertical');
	var parentList = element.parent();
	var children = parentList.children();

	// Start at 1 so we don't move the divider
	var pos = 1;

	// using length-1 so we do not move the add button
	// We are also assuming that we are not moving up past the top or down past the bottom

	var first;
	var last;

	while (pos < (children.length - 1)) {
		var myId = $(element).prop('id');
		if ((down && ($(children[pos]).prop('id') == myId)) || ((!down && ($(children[pos+1]).prop('id') == myId)))) {
			first = children[pos + 1];
			last = children[pos];
			parentList.append(children[pos + 1]);
			parentList.append(children[pos]);
			pos += 2;
			break;

		} else {
			parentList.append(children[pos]);
			pos++;
		}
	}
	// Add back the add button
	while (pos < children.length) {
		parentList.append(children[pos]);
		pos++;
	}

	if (first && last) {
		var suffix1 = findSuffix(first);
		var suffix2 = findSuffix(last);

		// Using a temp name so we don't lose our values by temporarily naming fields the same.
		changeSuffix(first, "-itemp");
		changeSuffix(last, suffix1);
		changeSuffix(first, suffix2);
	}

	enableButtons(parentList, maxInstances);
	parentList.listview();
	parentList.listview('refresh');
};

function findSuffix(element) {
	var suffix = '';

	var elem = $(element);
	var currId = elem.prop('name');
	if (currId != null && currId != '') {
		var dash = currId.lastIndexOf('-i');
		if (dash > 0) {
			suffix = currId.substring(dash);
		}
	}

	if (suffix == '') {
		elem.children().each(function() {
			if (suffix == '') {
				var temp = findSuffix($(this));
				if (temp != '') {
					suffix = temp;
				}
			}
		});
	}

	return suffix;
}

function changeSuffix(element, newSuffix) {
	var elem = $(element);
	var currId = elem.prop('id');
	var currName = elem.prop('name');

	if (currId != null && currId != '') {
		var idash = currId.lastIndexOf('-i');
		var baseId = currId;
		if (idash > 0) {
			baseId = currId.substring(0, idash);
		}
		elem.prop('id', baseId+newSuffix);
	}

	if (currName != null && currName != '') {
		var ndash = currName.lastIndexOf('-i');
		var baseName = currName;
		if (ndash > 0) {
			baseName = currName.substring(0, ndash);
		}
		elem.prop('name', baseName+newSuffix);
	}

	var currForId = elem.prop('for');
	if (currForId != null && currForId != '') {
		var fdash = currForId.lastIndexOf('-i');
		var baseForId = currForId;
		if (fdash > 0) {
			baseForId = currForId.substring(0, fdash);
		}
		elem.prop('for',baseForId+newSuffix).val('');
	}

	elem.children().each(function() {
		changeSuffix($(this), newSuffix);
	});
}

function booleanValue(value) {
	if (value === 'true') {
		return true;
	} else {
		return false;
	}
};

function parseDateCallback(callbackArgs) {
	var element = $(this.element);
	var val = element.val();
	if (!val) {
		return null;
	}
	val = selfservice.parseDate(element);
	if (val) {
		this.setTheDate(val);
	}
	return this.date;
}

var resizePdfjsViewer = function () {
	var footer = $("#ss-footer-box");
	if (!footer) {
		return;
	}
	if (!footer.offset()) {
		return;
	}
	var footerTop = footer.offset().top;

	var pdfjsiframe = $('iframe.ss-pdfjs-viewer');
	if (!pdfjsiframe) {
		return;
	}
	if (!pdfjsiframe.offset()) {
		return;
	}
	var imageViewerTop = pdfjsiframe.offset().top;

	var pdfjsHeight = footerTop - imageViewerTop - 6;
	if (pdfjsHeight <= 0) {
		pdfjsHeight = 980;
	}
	pdfjsiframe.css('height', pdfjsHeight);
};

var resizeViewer = _.debounce(resizePdfjsViewer, 300);

$.fn.inView = function(){
	//function checks if element is in viewport rect.top should be greater than 125 to take into account the SelfService header
	if(!this.length) return false;
	var rect = this.get(0).getBoundingClientRect();

	return (
		rect.top >= 125 &&
		rect.left >= 0 &&
		rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
		rect.right <= (window.innerWidth || document.documentElement.clientWidth)
	);
};