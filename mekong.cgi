#!/usr/bin/perl -w

use POSIX;
use CGI qw(:all);
use CGI::Carp qw(fatalsToBrowser warningsToBrowser);
use HTML::Template qw(:all);

$debug = 0;
$| = 1;

print page_header();
	
set_global_variables();
read_books($books_file);
set_page();

my $page = "main";
my $tmpl = HTML::Template->new(filename => "$tmpl_dir/$page.template");
$tmpl->param(%tmpl_variables);
print $tmpl->output();

print page_trailer();
exit 0;

sub set_page {
	my $action = param('action');

	#Get isbn when we want to add, drop or view details
	my $isbn = ();
	for my $param (param()) {
		if ($param =~ /action (\d{9}(\d|X))$/) {
			$isbn = $1;
			$action = param($param);
		} elsif ($param =~ /(\d{9}(\d|X))$/) {
			$isbn = $1;
		}
	}

	#Perform action
	if (defined $action) {
		if ($action eq "Login") {
			if (authenticate(param('login'), param('password'))) {
				$action = "Basket";
			}
		}
	
		if ($action =~ /New\s+Account/) {
			$tmpl_variables{NEW_ACCOUNT} = 1;
			$tmpl_variables{SCREEN} = "NEW_ACCOUNT";
		} elsif ($action =~ /Create\s+Account/) {
			if (create_account()) {
				$tmpl_variables{NEW_ACCOUNT} = 0;
				basket_command(param('login'));
				$tmpl_variables{BASKET} = 1;
				$tmpl_variables{SCREEN} = "BASKET";
			}
		} elsif ($action eq "search" && defined param('search_terms')) {
			my @results = search_results(param('search_terms'));
			$tmpl_variables{SEARCH} = 1;
			$tmpl_variables{SCREEN} = "SEARCH";
			$tmpl_variables{TERMS} = param('search_terms');
			$tmpl_variables{RESULTS} = \@results;
		} elsif ($action eq "Basket") {
			basket_command(param('login'));
			$tmpl_variables{BASKET} = 1;
			$tmpl_variables{SCREEN} = "BASKET";
		} elsif ($action =~ /Check\s+Out/) {
			if (checkout_command(param('login'))) {
				$tmpl_variables{CHECK_OUT} = 1;
				$tmpl_variables{SCREEN} = "CHECK_OUT";
			}
		} elsif ($action =~ /Finalise\s+Order/) {
			if (defined param('login') && finalise_order(param('login'))) {
				basket_command(param('login'));
				$tmpl_variables{BASKET} = 1;
				$tmpl_variables{SCREEN} = "BASKET";
			}
		} elsif ($action eq "Orders") {
			my @orders = orders_command(param('login'));
			$tmpl_variables{SCREEN} = "ORDERS";
			$tmpl_variables{ORDERS} = \@orders;
		} elsif ($action eq "Logout") {
			%tmpl_variables = ();
			%user_details = ();
		} elsif ($action eq "Add") {
			#Add isbn to basket
			if (defined param('login') && param('login') ne "") {
				add_command(param('login'), $isbn);
			} else {
				$tmpl_variables{ERROR} = "Please Login or Create Account.";
			}
		} elsif ($action eq "Drop") {
			#Remove isbn from basket then load again
			drop_command(param('login'), $isbn);
		} elsif ($action eq "Details") {
			details_command($isbn);
			$tmpl_variables{SCREEN} = "DETAILS";
			$tmpl_variables{DETAILS} = 1;
		}
	}

	#If theres an error we want to view the last thing we saw
	if (defined $tmpl_variables{ERROR} && defined param('screen') && param('screen') ne "") {
		$tmpl_variables{param('screen')} = 1;
		$tmpl_variables{SCREEN} = param('screen');
		if (param('screen') eq "SEARCH") {
			my @results = search_results(param('search_terms_1'));
			$tmpl_variables{TERMS} = param('search_terms_1');
			$tmpl_variables{RESULTS} = \@results;
		} elsif (param('screen') eq "BASKET") {
			basket_command(param('login'));
			$tmpl_variables{BASKET} = 1;
			$tmpl_variables{SCREEN} = "BASKET";
		} elsif (param('screen') eq "CHECK_OUT") {
			if (checkout_command(param('login'))) {
				$tmpl_variables{CHECK_OUT} = 1;
				$tmpl_variables{SCREEN} = "CHECK_OUT";
			} else {
				basket_command(param('login'));
				$tmpl_variables{BASKET} = 1;
				$tmpl_variables{CHECK_OUT} = 0;
				$tmpl_variables{SCREEN} = "BASKET";
			}
		} elsif (param('screen') eq "ORDERS") {
			my @orders = orders_command(param('login'));
			$tmpl_variables{SCREEN} = "ORDERS";
			$tmpl_variables{ORDERS} = \@orders;
		} elsif (param('screen') eq "DETAILS") {
			details_command($isbn);
			$tmpl_variables{SCREEN} = "DETAILS";
			$tmpl_variables{DETAILS} = 1;
		}
	}

}

################################################
# Functions for Login
################################################
sub legal_login {
	my ($login) = @_;
	
	if ($login !~ /^[a-zA-Z][a-zA-Z0-9]*$/) {
		$tmpl_variables{ERROR} = "Invalid login '$login': logins must start with a letter and contain only letters and digits.";
		return 0;
	}
	if (length $login < 3 || length $login > 8) {
		$tmpl_variables{ERROR} = "Invalid login: logins must be 3-8 characters long.";
		return 0;
	}

	return 1;
}

#Checks login is legal and login exists
sub legal_login_exists {
	my ($login) = @_;
	
	if ($login !~ /^[a-zA-Z][a-zA-Z0-9]*$/) {
		$tmpl_variables{ERROR} = "Invalid login '$login': logins must start with a letter and contain only letters and digits.";
		return 0;
	}
	if (length $login < 3 || length $login > 8) {
		$tmpl_variables{ERROR} = "Invalid login: logins must be 3-8 characters long.";
		return 0;
	}
	if (!(-e "$users_dir/$login")) {
		$tmpl_variables{ERROR} = "User '$login' does not exist.";
		return 0;
	}
	return 1;
}

# return true if specified string can be used as a password
sub legal_password {
	my ($password) = @_;
	
	if ($password =~ /\s/) {
		$tmpl_variables{ERROR} = "Invalid password: password can not contain white space.";
		return 0;
	}
	if (length $password < 5) {
		$tmpl_variables{ERROR} = "Invalid password: passwords must contain at least 5 characters.";
		return 0;
	}
	return 1;
}

#Authenticate user
sub authenticate {
	my ($login, $password) = @_;
	our (%user_details);
	
	if (legal_login_exists($login) && legal_password($password)) {
		# Can assume that file exists since we checked in legal_login
		%details = set_user_details($login);
		
		foreach $field (qw(name street city state postcode password)) {
			if (!defined $details{$field}) {
	 	 	 	$tmpl_variables{ERROR} = "Incomplete user file: field $field missing";
				return 0;
			}
		}

		if ($details{"password"} ne $password) {
	  	 	$tmpl_variables{ERROR} = "Incorrect password.";
	  	 	$tmpl_variables{LOGIN} = ();
			return 0;
		}
		
		%user_details = %details;
	  	return 1;
	}
	
	return 0;
}
################################################

################################################
# Functions to create a new account
################################################
sub create_account {
	my $login = param('login');
	my $password = param('password');
	my $name = param('name');
	my $street = param('street');
	my $city = param('city');
	my $state = param('state');
	my $postcode = param('postcode');
	my $email = param('email');
	
	if (! ($login && $password && $name && $street && 
	       $city && $state && $postcode && $email)) {
		$tmpl_variables{ERROR} = "Not All Field Filled Out";
		return 0;
	}
	if (!legal_login($login) || !legal_password($password)) {
		return 0;
	}
	if (-r "$users_dir/$login") {
		$tmpl_variables{ERROR} = "Invalid user name: login already exists.";
		return 0;
	}
	if ($login eq $password) {
		$tmpl_variables{ERROR} = "Login can not be the same as your Password";
		return 0;
	}
	if (!open(USER, ">$users_dir/$login")) {
		$tmpl_variables{ERROR} = "Can not create user file $users_dir/$login: $!";
		return 0;
	}
	
	foreach $description (@new_account_rows) {
		my ($field, $label)  = split /\|/, $description;
		next if $field eq "login";
		my $value = ();
		if ($field eq "password") {
			$value = $password;
		} elsif ($field eq "name") {
			$value = $name;
		} elsif ($field eq "street") {
			$value = $street;
		} elsif ($field eq "city") {
			$value = $city;
		} elsif ($field eq "state") {
			$value = $state;
		} elsif ($field eq "postcode") {
			$value = $postcode;
		} elsif ($field eq "email") {
			$value = $email;
		}
		$user_details{$field} = $value;
		print USER "$field=$value\n";
	}
	close(USER);
	$tmpl_variables{LOGIN} = $login;
	return 1;
}
################################################

################################################
#Functions for searching
################################################
# ascii display of search results
sub search_results {
	my ($search_terms) = @_;
	my @matching_isbns = search_books($search_terms);
	return get_book_descriptions(0, @matching_isbns);
}

# return books matching search string
sub search_books {
	my ($search_string) = @_;
	$search_string =~ s/\s*$//;
	$search_string =~ s/^\s*//;
	return search_books1(split /\s+/, $search_string);
}

# return books matching search terms
sub search_books1 {
	my (@search_terms) = @_;
	our %book_details;
	print STDERR "search_books1(@search_terms)\n" if $debug;
	my @unknown_fields = ();
	foreach $search_term (@search_terms) {
		push @unknown_fields, "'$1'" if $search_term =~ /([^:]+):/ && !$attribute_names{$1};
	}
	printf STDERR "$0: warning unknown field%s: @unknown_fields\n", (@unknown_fields > 1 ? 's' : '') if @unknown_fields;
	my @matches = ();
	BOOK: foreach $isbn (sort keys %book_details) {
		my $n_matches = 0;
		if (!$book_details{$isbn}{'=default_search='}) {
			$book_details{$isbn}{'=default_search='} = ($book_details{$isbn}{title} || '')."\n".($book_details{$isbn}{authors} || '');
			print STDERR "$isbn default_search -> '".$book_details{$isbn}{'=default_search='}."'\n" if $debug;
		}
		print STDERR "search_terms=@search_terms\n" if $debug > 1;
		foreach $search_term (@search_terms) {
			my $search_type = "=default_search=";
			my $term = $search_term;
			if ($search_term =~ /([^:]+):(.*)/) {
				$search_type = $1;
				$term = $2;
			}
			print STDERR "term=$term\n" if $debug > 1;
			while ($term =~ s/<([^">]*)"[^"]*"([^>]*)>/<$1 $2>/g) {}
			$term =~ s/<[^>]+>/ /g;
			next if $term !~ /\w/;
			$term =~ s/^\W+//g;
			$term =~ s/\W+$//g;
			$term =~ s/[^\w\n]+/\\b +\\b/g;
			$term =~ s/^/\\b/g;
			$term =~ s/$/\\b/g;
			next BOOK if !defined $book_details{$isbn}{$search_type};
			print STDERR "search_type=$search_type term=$term book=$book_details{$isbn}{$search_type}\n" if $debug;
			my $match;
			eval {
				my $field = $book_details{$isbn}{$search_type};
				# remove text that looks like HTML tags (not perfect)
				while ($field =~ s/<([^">]*)"[^"]*"([^>]*)>/<$1 $2>/g) {}
				$field =~ s/<[^>]+>/ /g;
				$field =~ s/[^\w\n]+/ /g;
				$match = $field !~ /$term/i;
			};
			if ($@) {
				$last_error = $@;
				$last_error =~ s/;.*//;
				return (); 
			}
			next BOOK if $match;
			$n_matches++;
		}
		push @matches, $isbn if $n_matches > 0;
	}
	
	sub bySalesRank {
		my $max_sales_rank = 100000000;
		my $s1 = $book_details{$a}{SalesRank} || $max_sales_rank;
		my $s2 = $book_details{$b}{SalesRank} || $max_sales_rank;
		return $a cmp $b if $s1 == $s2;
		return $s1 <=> $s2;
	}
	
	return sort bySalesRank @matches;
}

# return descriptions of specified books
sub get_book_descriptions {
	my ($order, @isbns) = @_;
	my @books = ();
	our %book_details;
	foreach $isbn (@isbns) {
		my $authors = $book_details{$isbn}{authors} || "";
		$authors =~ s/\n([^\n]*)$/ & $1/g;
		$authors =~ s/\n/, /g;

		my %book = ();
		$book{IMAGE} = $book_details{$isbn}{smallimageurl} || "";
		$book{HEIGHT} = $book_details{$isbn}{smallimageheight} || "";
		$book{WIDTH} = $book_details{$isbn}{smallimagewidth} || "";
		$book{TITLE} = $book_details{$isbn}{title} || "";
		$book{AUTHORS} = $authors;
		$book{PRICE} = $book_details{$isbn}{price} || "";
		if (!$order) {
			$book{ISBN} = $isbn;
		}
		
		push(@books, \%book);
	}
	return @books;
}
################################################

################################################
# FUnctions for the basket
################################################
sub basket_command {
	my ($login) = @_;
	my @basket_isbns = read_basket($login);
	if (!@basket_isbns) {
		$tmpl_variables{MESSAGE} = "Your Shopping Basket is empty.\n";
	} else {
		$tmpl_variables{MESSAGE} = "Your Shopping Basket\n";
		my @results = get_book_descriptions(0, @basket_isbns);
		$tmpl_variables{RESULTS} = \@results;
		$tmpl_variables{TOTAL} = total_books(@basket_isbns);
	}
}

# return books in specified user's basket
sub read_basket {
	my ($login) = @_;
	our %book_details;
	open F, "$baskets_dir/$login" or return ();
	my @isbns = <F>;

	close(F);
	chomp(@isbns);
	!$book_details{$_} && die "Internal error: unknown isbn $_ in basket\n" foreach @isbns;
	return @isbns;
}

# return total cost of specified books
sub total_books {
	my @isbns = @_;
	our %book_details;
	$total = 0;
	foreach $isbn (@isbns) {
		die "Internal error: unknown isbn $isbn  in total_books" if !$book_details{$isbn}; # shouldn't happen
		my $price = $book_details{$isbn}{price};
		$price =~ s/[^0-9\.]//g;
		$total += $price;
	}
	return $total;
}
################################################

################################################
# Functions for check out
################################################
sub checkout_command {
	my ($login) = @_;
	our %user_details;
	my @basket_isbns = read_basket($login);
	if (!@basket_isbns) {
		$tmpl_variables{ERROR} = "Can not checkout: your basket is empty.";
		return 0;
	}
	my @results = get_book_descriptions(0, @basket_isbns);
	$tmpl_variables{RESULTS} = \@results;
	$tmpl_variables{MESSAGE} = "Basket";
	$tmpl_variables{FULLNAME} = $user_details{'name'};
	$tmpl_variables{STREET} = $user_details{'street'};
	$tmpl_variables{CITY} = $user_details{'city'};
	$tmpl_variables{STATE} = $user_details{'state'};
	$tmpl_variables{POSTCODE} = $user_details{'postcode'};
	$tmpl_variables{TOTAL} = total_books(@basket_isbns);
	return 1;
}
# return books in specified user's basket
sub read_basket {
	my ($login) = @_;
	our %book_details;
	open F, "$baskets_dir/$login" or return ();
	my @isbns = <F>;

	close(F);
	chomp(@isbns);
	!$book_details{$_} && die "Internal error: unknown isbn $_ in basket\n" foreach @isbns;
	return @isbns;
}
################################################

################################################
# Functions for finalising orders
################################################
sub finalise_order{
	my ($login) = @_;
	my $credit_card_number = param('credit_card_number');
	my $expiry_date = param('expiry_date');
	
	if (!(defined $credit_card_number && defined $expiry_date)) {
		$tmpl_variables{ERROR} = "Please Enter Credit Card and Expiry Date.";
		return 0;
	}
	
	if (length $credit_card_number != 16) {
		$tmpl_variables{ERROR} = "Invalid credit card number - must be 16 digits.";
		return 0;
	}
	
	if ($credit_card_number !~ /^\d{16}$/) {
		$tmpl_variables{ERROR} = "Invalid credit card number - must be 16 digits.";
		return 0;
	}
	
	if ($expiry_date !~ /\d{2}\/\d{2}/) {
		$tmpl_variables{ERROR} = "Invalid Expiry Date.";
		return 0;
	}
	
	#Need to check expiry date is valid
	if (!legal_expiry($expiry_date)) {
		return 0;
	}
	
	my $order_number = 0;

	if (open ORDER_NUMBER, "$orders_dir/NEXT_ORDER_NUMBER") {
		$order_number = <ORDER_NUMBER>;
		chomp $order_number;
		close(ORDER_NUMBER);
	}
	$order_number++ while -r "$orders_dir/$order_number";
	open F, ">$orders_dir/NEXT_ORDER_NUMBER" or die "Can not open $orders_dir/NEXT_ORDER_NUMBER: $!\n";
	print F ($order_number + 1);
	close(F);

	my @basket_isbns = read_basket($login);
	if (@basket_isbns == ()) {
		$tmpl_variables{ERROR} = "Basket is empty!";
		return 0;
	}
	open ORDER,">$orders_dir/$order_number" or die "Can not open $orders_dir/$order_number:$! \n";
	print ORDER "order_time=".time()."\n";
	print ORDER "credit_card_number=$credit_card_number\n";
	print ORDER "expiry_date=$expiry_date\n";
	print ORDER join("\n",@basket_isbns)."\n";
	close(ORDER);
	unlink "$baskets_dir/$login";
	
	open F, ">>$orders_dir/$login" or die "Can not open $orders_dir/$login:$! \n";
	print F "$order_number\n";
	close(F);
	return 1;
}

sub legal_expiry {
	my ($expiry_date) = @_;
	($sec,$min,$hour,$mday,$mon,$year,$wday,$yday,$isdst) = localtime(time);
	$year += 1900;
	$mon += 1;
	$year =~ s/\d{2}(\d{2})/$1/;
	if ($expiry_date =~ /(\d{2})\/(\d{2})/) {
		$given_mon = $1;
		$given_year = $2;
		if ($given_year < $year) {
			$tmpl_variables{ERROR} = "Invalid Expiry Date - Year Expired";
			return 0;
		} elsif ($given_year == $year) {
			if ($given_mon < $mon) {
				$tmpl_variables{ERROR} = "Invalid Expiry Date - Year Expired";
				return 0;
			}
		}
	}
	return 1;
}
################################################

################################################
# Functions for orders
################################################
sub orders_command {
	my ($login) = @_;
	
	@order_num = login_to_orders($login);
	if (@order_num) {
		@orders = ();
		foreach $order (login_to_orders($login)) {
			my ($order_time, $credit_card_number, $expiry_date, @isbns) = read_order($order);
			$order_time = localtime($order_time);
			my %order = ();
			$order{ORDER} = "Order #$order - $order_time";
			$order{CREDIT_CARD} = "Credit Card Number: $credit_card_number (Expiry $expiry_date)";
			my @results = get_book_descriptions(1, @isbns);
			$order{RESULTS} = \@results;
			$order{TOTAL} = total_books(@isbns);
			push (@orders, \%order);
		}
		return @orders;
	} else {
		$tmpl_variables{ERROR} = "You have made no orders";
		return;
	}
}

# return order numbers for specified login
sub login_to_orders {
	my ($login) = @_;
	open F, "$orders_dir/$login" or return ();
	@order_numbers = <F>;
	close(F);
	chomp(@order_numbers);
	return @order_numbers;
}

# return contents of specified order
sub read_order {
	my ($order_number) = @_;
	open F, "$orders_dir/$order_number" or warn "Can not open $orders_dir/$order_number:$! \n";
	@lines = <F>;
	close(F);
	chomp @lines;
	foreach (@lines[0..2]) {s/.*=//};
	return @lines;
}
################################################

################################################
# FUnction to add book
################################################
sub add_command {
	my ($login, $isbn) = @_;
	our %book_details;
	if (!legal_isbn($isbn)) {
		return;
	}
	if (!$book_details{$isbn}) {
		$tmpl_variables{ERROR} = "Unknown isbn: $isbn.";
		return;
	}
	add_basket($login, $isbn);
	$tmpl_variables{ERROR} = "Added to Basket.";
}

# add specified book to specified user's basket
sub add_basket {
	my ($login, $isbn) = @_;
	open F, ">>$baskets_dir/$login" or die "Can not open $baskets_dir/$login::$! \n";
	print F "$isbn\n";
	close(F);
}

# return true if specified string could be an ISBN
sub legal_isbn {
	my ($isbn) = @_;
	return 1 if $isbn =~ /^\d{9}(\d|X)$/;
	$tmpl_variables{ERROR} = "Invalid isbn '$isbn' : an isbn must be exactly 10 digits.";
	return 0;
}
################################################

################################################
# Functions to drop a book
################################################
sub drop_command {
	my ($login, $isbn) = @_;
	my @basket_isbns = read_basket($login);
	if (!legal_isbn($isbn)) {
		print "$last_error\n";
		return;
	}
	if (!grep(/^$isbn$/, @basket_isbns)) {
		print "Isbn $isbn not in shopping basket.\n";
		return;
	}
	delete_basket($login, $isbn);
	$tmpl_variables{ERROR} = "Book Dropped.";
}

# delete specified book from specified user's basket
# only first occurance is deleted

sub delete_basket {
	my ($login, $delete_isbn) = @_;
	my @isbns = read_basket($login);
	open F, ">$baskets_dir/$login" or die "Can not open $baskets_dir/$login: $!";
	foreach $isbn (@isbns) {
		if ($isbn eq $delete_isbn) {
			$delete_isbn = "";
			next;
		}
		print F "$isbn\n";
	}
	close(F);
	unlink "$baskets_dir/$login" if ! -s "$baskets_dir/$login";
}
################################################

################################################
# Function for details
################################################
sub details_command {
	my ($isbn) = @_;
	our %book_details;
	if (!legal_isbn($isbn)) {
		return;
	}
	if (!$book_details{$isbn}) {
		$tmpl_variables{ERROR} = "Unknown isbn: $isbn.";
		return;
	}
	
	$tmpl_variables{TITLE} = $book_details{$isbn}{title} || "";
	my $authors = $book_details{$isbn}{authors} || "";
	$authors =~ s/\n([^\n]*)$/ & $1/g;
	$authors =~ s/\n/, /g;
	$tmpl_variables{AUTHORS} = $authors;
	$tmpl_variables{DESCRIPTION} = $book_details{$isbn}{productdescription} || "";
	$tmpl_variables{IMAGE} = $book_details{$isbn}{largeimageurl} || "";
	$tmpl_variables{HEIGHT} = $book_details{$isbn}{largeimageheight} || "";
	$tmpl_variables{WIDTH} = $book_details{$isbn}{largeimagewidth} || "";
	$tmpl_variables{BINDING} = $book_details{$isbn}{binding} || "";
	$tmpl_variables{CATALOG} = $book_details{$isbn}{catalog} || "";
	$tmpl_variables{EAN} = $book_details{$isbn}{ean} || "";
	$tmpl_variables{ISBN} = $isbn || "";
	$tmpl_variables{NUMPAGES} = $book_details{$isbn}{numpages} || "";
	$tmpl_variables{PRICE} = $book_details{$isbn}{price} || "";
	$tmpl_variables{PUBLICATION} = $book_details{$isbn}{publication_date} || "";
	$tmpl_variables{PUBLISHER} = $book_details{$isbn}{publisher} || "";
	$tmpl_variables{SALESRANK} = $book_details{$isbn}{salesrank} || "";
	$tmpl_variables{YEAR} = $book_details{$isbn}{year} || "";
}
################################################

sub set_user_details {
	my ($login) = @_;
	my %details = ();
	if (!open(USER, "$users_dir/$login")) {
		$tmpl_variables{ERROR} = "Can not open user file $users_dir/$login: $!";
	} else {
		$tmpl_variables{LOGIN} = $login;
		while ($field = <USER>) {
			chomp $field;
			if ($field =~ /^(\w*)=(.*)$/) {
				$details{$1} = $2;
			}
		}
		close(USER);
	}
	return %details;
}

sub set_global_variables {
	$base_dir = ".";
	$books_file = "$base_dir/books.json";
	mkdir $books_file if !-d $books_file;
	$orders_dir = "$base_dir/orders";
	mkdir $books_file if !-d $books_file;
	$baskets_dir = "$base_dir/baskets";
	mkdir $baskets_dir if !-d $baskets_dir;
	$users_dir = "$base_dir/users";
	mkdir $users_dir if !-d $users_dir;
	$tmpl_dir = "$base_dir/templates";
	mkdir $tmpl_dir if !-d $tmpl_dir;
	$last_error = "";
	%book_details = ();
	%attribute_names = ();
	%tmpl_variables = ();
	my $login = param('login');
	my $password = param('password');
	%user_details = set_user_details($login) if (defined $login && !defined $password && (-e "$users_dir/$login") && legal_login_exists($login));
	@new_account_rows = (
		  'login|Login:|10',
		  'password|Password:|10',
		  'name|Full Name:|50',
		  'street|Street:|50',
		  'city|City/Suburb:|25',
		  'state|State:|25',
		  'postcode|Postcode:|25',
		  'email|Email Address:|35'
		  );
}

# read contents of files in the books dir into the hash book
# a list of field names in the order specified in the file 
sub read_books {
	my ($books_file) = @_;
	our %book_details;
	print STDERR "read_books($books_file)\n" if $debug;
	open BOOKS, $books_file or die "Can not open books file '$books_file'\n";
	my $isbn;
	while (<BOOKS>) {
		if (/^\s*"(\d+X?)"\s*:\s*{\s*$/) {
			$isbn = $1;
			next;
		}
		next if !$isbn;
		my ($field, $value);
		if (($field, $value) = /^\s*"([^"]+)"\s*:\s*"(.*)",?\s*$/) {
			$attribute_names{$field}++;
			print STDERR "$isbn $field-> $value\n" if $debug > 1;
			$value =~ s/([^\\]|^)\\"/$1"/g;
	  		$book_details{$isbn}{$field} = $value;
		} elsif (($field) = /^\s*"([^"]+)"\s*:\s*\[\s*$/) {
			$attribute_names{$1}++;
			my @a = ();
			while (<BOOKS>) {
				last if /^\s*\]\s*,?\s*$/;
				push @a, $1 if /^\s*"(.*)"\s*,?\s*$/;
			}
	  		$value = join("\n", @a);
			$value =~ s/([^\\]|^)\\"/$1"/g;
	  		$book_details{$isbn}{$field} = $value;
	  		print STDERR "book{$isbn}{$field}=@a\n" if $debug > 1;
		}
	}
	close BOOKS;
}

#
# HTML at top of every screen
#
sub page_header() {
	return <<eof;
Content-Type: text/html

<!DOCTYPE html>
<html lang="en">
<head>
<title>Mekong</title>
eof
}

#
# HTML at bottom of every screen
#
sub page_trailer() {
	return <<eof;
</body>
</html>
eof
}
