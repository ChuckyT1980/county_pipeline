function reloadShoppingCart(cartPanelDiv) {
	var cartPanel = $(cartPanelDiv).parent();
	var cartUrl = $(cartPanelDiv).data('cartUrl');
	cartPanelDiv.load(cartUrl, function() {
		cartPanelDiv.trigger('create');
		cartPanel.trigger('updatelayout');
		$.mobile.activePage.trigger('refresh');
		$(cartPanel).css("height", $( window ).height() - 20 );
	});
	
	setTimeout(function() { 
		if (isCartEmpty()) {
			$("[id$='customerInfoGroup'").hide();
			$("[id$='customerInfoGroup'").prev().hide();
		}
	}, 40);
}

function isCartEmpty() {
	// does the count label contain a number?
	var regex = /\d/g;
	var containsNumber = regex.test($('#ss-cart-count-label').text());

	if ($("a[data-icon='delete']").size() === 0 || !containsNumber) {
		return true;
	}
	
	return false;
}

function updateCartIcon(itemCount) {
	if (itemCount > 0) {
		$('#ss-cart-count-label').text(itemCount);

		// bounce the cart count label
		$('#ss-cart-count-label').animate({bottom: '+=0.8em'}, 150);
		$('#ss-cart-count-label').animate({bottom: '-=0.8em'}, 100);
		$('#ss-cart-count-label').animate({bottom: '+=0.4em'}, 100);
		$('#ss-cart-count-label').animate({bottom: '-=0.4em'}, 75);
	} else {
		$('#ss-cart-count-label').text('\u00a0');
	}
}

function clearCart(popupId, cartPanel) {
	var path = window.location.pathname;
	var prefix=path.substring(0, path.indexOf('/', 1));

	$.ajax({
		url: prefix + '/clearCart',
		type: 'POST',
		error: function(jqXHR, textStatus, errorThrown) {
			removalFailed(popupId);
		},
		success: function() {
			var span = $('#ss-cart-count-label');
			span.text('');

			// clear the cart
			reloadShoppingCart(cartPanel);
			updateCartIcon(0);
		}
	});
}

function clearSaveItems(popupId, cartPanel) {
	var path = window.location.pathname;
	var prefix=path.substring(0, path.indexOf('/', 1));

	$.ajax({
		url: prefix + '/clearSavedItems',
		type: 'POST',
		error: function(jqXHR, textStatus, errorThrown) {
			removalFailed(popupId);
		},
		success: function() {
			reloadShoppingCart(cartPanel);
		}
	});
}

function confirmClearCart(popupId, cartPanel) {
	$('body').data('confirmed', false);
	
	$('#' + popupId).popup({
		afterclose: function() {
			if($('body').data('confirmed')) {
				clearCart(popupId, cartPanel);
			}
		}
	})
	
	$('#' + popupId).popup('open', {transition: 'pop'});
}

function confirmClearSaveItems(popupId, cartPanel) {
	$('body').data('confirmed', false);
	
	$('#' + popupId).popup({
		afterclose: function() {
			if($('body').data('confirmed')) {
				clearSaveItems(popupId, cartPanel);
			}
		}
	})
	
	$('#' + popupId).popup('open', {transition: 'pop'});
}


function confirmRemoveCartItem(popupId, cartPanel, itemId, isReloadPage) {
	$('body').data('confirmed', false);
	$('body').data('selectedItem', itemId);
		
	$('#' + popupId).popup({
		afterclose: function() {
			if ($('body').data('confirmed')) {
				removeCartItem(popupId, cartPanel, isReloadPage);
			}
		}
	});
			
	$('#' + popupId).popup('open', {transition: 'pop'});
}

function verifyCartItemQuantities(el, minValue, maxValue) {
	var cartItemQuantityElements = $("input[id$='cartItemQuantity']");
	var quantityIsInvalid = false;
	
	for (var i = 0; i < cartItemQuantityElements.length; i++) {
		if (parseInt(cartItemQuantityElements[i].value) < minValue || 
				parseInt(cartItemQuantityElements[i].value) > maxValue ||
				cartItemQuantityElements[i].value === '') {
			addFieldErrors(undefined, $('#' + cartItemQuantityElements[i].id), undefined);
			quantityIsInvalid = true;
		} else {
			clearErrors(undefined, $('#' + cartItemQuantityElements[i].id));
		}
	}
	
	if (quantityIsInvalid) {
		$('#shoppingCartProductQuantityError').popup('open', {transition: 'pop'});
		return;
	}
	
	// redirect to the checkout review page
	document.location.href = el.name;
}

function verifyCartItemQuantity(id, minValue, maxValue) {
	var cartItem = $('#' + id);
	
	if (parseInt(cartItem.val()) < minValue || 
			parseInt(cartItem.val()) > maxValue ||
			cartItem.val() === '') {
		addFieldErrors(undefined, cartItem, undefined);
		$('#shoppingCartProductQuantityError').popup('open', {transition: 'pop'});
	} else {
		clearErrors(undefined, cartItem);
	}
}

function removeConfirmed(popupId) {
	$('body').data('confirmed', true);
	closePopup(popupId);
}

function closePopup(popupId) {
	$('#' + popupId).popup('close', {transition: 'pop'});
}

function removalFailed(popupId) {
	$('#' + popupId + 'Failed').popup('open', {transition: 'pop'});
}
	
function removeCartItem(popupId, cartPanel, isReloadPage) {
	var itemId = $('body').data('selectedItem');
	var path = window.location.pathname;
	var prefix=path.substring(0, path.indexOf('/', 1));

	$.ajax({
		url: prefix + '/removeCartItem?id=' + itemId,
		dataType: 'json',
		error: function(jqXHR, textStatus, errorThrown) {

			removalFailed(popupId);
		},
		success:function(data) {
			reloadShoppingCart(cartPanel);
			updateCartIcon(data);			
			
			if (isReloadPage !== undefined && isReloadPage === true) {
				window.location.reload(true);
			}
		}
	});
	return false;
}

function saveCartItemForLater(href, cartItem, markSaved, isEmbeddedCart) {
	var path = window.location.pathname;
	var prefix=path.substring(0, path.indexOf('/', 1));
	
	if(!isEmbeddedCart){
		$.ajax({
			url: prefix + '/saveCartItem/' + cartItem + '/' + isEmbeddedCart,
			type: 'POST',
			error: function(jqXHR, textStatus, errorThrown) {
			
				alert(messageStrings[selectedLanguage].Page_cart_message_saveFailed);
			},
			success:function(resultObject) {
				
				if (resultObject.updateCartItemErrorMessage !== undefined) {
					/* This can happen if the item was not found, such as when coming from the purchase screen.
					 * It isn't an error the user needs to be concerned with.
					 */
					console.log('Cart item ' + cartItem + ' not found, could not save for later, ' + resultObject.updateCartItemErrorMessage);
					return;
				}
				
				$('[id$=shoppingCartView]').html($(resultObject).find('[id$=shoppingCartView]').html());
				$('[id$=savedItemsViewHeader]').html($(resultObject).find('[id$=savedItemsViewHeader]').html());
				$('[id$=shoppingCartViewHeader]').html($(resultObject).find('[id$=shoppingCartViewHeader]').html());
				$('[id$=export-popup]').attr('id', $(resultObject).find('[id$=export-popup]').attr('id'));
				$('[id$=savedItemsView]').html($(resultObject).find('[id$=savedItemsView]').html());
				$('[id$=savedItemsView], [id$=shoppingCartView], [id$=savedItemsViewHeader], [id$=shoppingCartViewHeader]').enhanceWithin();
				$('[id$=savedItemsView], [id$=shoppingCartView], [id$=savedItemsViewHeader], [id$=shoppingCartViewHeader]').listview('refresh');
				
				$('#ss-cart-total').html($(resultObject).find('#ss-cart-total').html());
			}
		});
	}else{
		$.ajax({
			url: prefix + '/saveCartItem/' + cartItem + '/' + isEmbeddedCart,
			type: 'POST',
			error: function(jqXHR, textStatus, errorThrown) {
				alert(messageStrings[selectedLanguage].Page_cart_message_saveFailed);
			},
			success:function(resultObject) {
				if (resultObject.updateCartItemErrorMessage !== undefined) {
					/* This can happen if the item was not found, such as when coming from the purchase screen.
					 * It isn't an error the user needs to be concerned with.
					 */
					console.log('Cart item ' + cartItem + ' not found, could not save for later, ' + resultObject.updateCartItemErrorMessage);
					return;
				}
				
				updateCartIcon(resultObject.itemCount);
				reloadShoppingCart($('[id$=cartPanelInternal'));
			}
		});
		
		
	}
	
	return true;
}

// For slide out side Shopping Cart
function updateCartItemNumberOfCopies(evt) {
	var cartItemId = $(evt.target).attr('name');
	var productQty = ($(evt.target).val() != '') ? $(evt.target).val() : 0;	

	if (parseInt(productQty) === 0 || productQty === undefined || isNaN(productQty)) {
		return;
	}
	
	var maxLength = 3;
	if (productQty.length > maxLength) {
		var acceptableLengthValue = $(evt.target).val().substr(0, maxLength);
		$(evt.target).val(acceptableLengthValue);
		productQty = acceptableLengthValue; 
	}
	
	var path = window.location.pathname;
	var prefix = path.substring(0, path.indexOf('/', 1));
	var productCostUrl = prefix + '/updateCartItemQuantity/' + cartItemId + '/' + productQty;

	$.ajax({
		type: 'POST',
		url: productCostUrl,		
		dataType: 'json',
		success: function(resultObject) {
			if (resultObject.updateCartItemErrorMessage !== undefined) {
				/* This can happen if the item was not found, such as when coming from the purchase screen.
				 * It isn't an error the user needs to be concerned with.
				 */
				console.log('Cart item ' + cartItemId + ' not found, could not update item cost, ' + resultObject.updateCartItemErrorMessage);
				return;
			}
			
			var cartItemCost = resultObject.updatedCartItemCost;
			var cartTotal = resultObject.cartTotal;
			$('#' + cartItemId + '-cartItemCost').parent().css('margin', '7.2px');
			$('#' + cartItemId + '-cartItemCost').text(cartItemCost);
			
			if ($('.ss-cart-total').length > 0) {				
				$('.ss-cart-total').text(messageStrings[selectedLanguage].Page_cart_message_total + ' $' + cartTotal);
			}
			
			if ($('.ss-side-panel-cart-total').length > 0) {
				var text = $('.ss-side-panel-cart-total').text().split('$'); 
				$('.ss-side-panel-cart-total').text(text[0] + ' $' + cartTotal);
			}
		},
		error: function(jqXHR, textStatus, errorThrown) {
			alert(messageStrings[selectedLanguage].Page_document_message_cart_totalFailed);
		}
	});		
}


