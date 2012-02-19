var appendNavLinks = function() {
  var path           = document.location.pathname,
      parts          = path.split(/\d+/),
      commit_number  = parseInt(path.replace(parts[0], '').replace(parts[1], '')),
      next           = commit_number+1,
      prev           = commit_number-1,
      prevNavElement = $("<li><a class=\"pullreqnav\" href=\"" + parts[0] + prev + "/files" + "\">&laquo;</a></li>"),
      nextNavElement = $("<li><a class=\"pullreqnav\" href=\"" + parts[0] + next + "/files" + "\">&raquo;</a></li>");                 
  $(".js-hard-tabs").after(prevNavElement).after(nextNavElement);
}

$(function(){
  appendNavLinks();

  // TODO: use parts[1] to stay on te same page context user is currently on
  // $(".js-hard-tabs li a:not(.pullreqnav)").click(function(e){
  //   console.log("it's happening");
  //   $(".pullreqnav").remove();
  //   appendNavLinks();
  // });
  
  $(".pullreqnav").click(function(e){
    document.location = e.target;
  });
});
